"""
RAG（Retrieval-Augmented Generation）サービスモジュール。
クエリ分析、ベクトル検索、リランク、テキスト生成を組み合わせた
RAG パイプラインを提供する。
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure import bedrock_client, qdrant_client
from app.infrastructure.config import config
from app.models.database import Message, Session, User, UserMemory
from app.services.oracle_query import (
    OracleQueryResult,
    OracleUnavailableError,
    process_oracle_query,
)
from app.services.output_formatter import (
    format_table_data,
    save_output,
    suggest_chart_config,
)
from app.services.text_normalizer import normalize_query

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# データクラス
# ---------------------------------------------------------------------------


@dataclass
class QueryAnalysis:
    """クエリ分析結果を保持するデータクラス。"""

    intent: str  # DOC_SEARCH | ORACLE_QUERY | HYBRID
    normalized_query: str
    translated_query: str
    filters: dict  # {site_code, line_code, process_codes}
    expanded_queries: list[str] = field(default_factory=list)


@dataclass
class RagSearchResult:
    """RAG 検索結果を保持するデータクラス。"""

    content: str
    document_id: str
    document_name: str
    section_title: str
    score: float
    chunk_id: str


# ---------------------------------------------------------------------------
# クエリ分析プロンプト
# ---------------------------------------------------------------------------

_INTENT_SYSTEM_PROMPT = """\
あなたはクエリ分析AIです。ユーザーのクエリを以下の3種類の意図に分類し、
フィルタ条件（サイト、ライン、工程）を抽出してください。

意図の種類:
- DOC_SEARCH: ドキュメント検索が必要なクエリ（手順書、規格書、マニュアル等）
- ORACLE_QUERY: データベースへのデータ照会が必要なクエリ（実績データ、品質データ等）
- HYBRID: 両方必要なクエリ

{user_context}

ユーザー情報に用語の対応関係（例: 通称→正式名称、ラインコード等）が含まれている場合は、
クエリ中の用語をそれに基づいて解釈し、正しいフィルタ値を抽出してください。

以下のJSON形式のみで返答してください（説明文不要）:
{{
  "intent": "DOC_SEARCH" | "ORACLE_QUERY" | "HYBRID",
  "site_code": null または "サイトコード文字列",
  "line_code": null または "ラインコード文字列",
  "process_codes": [] または ["工程コード1", "工程コード2"]
}}
"""


# ---------------------------------------------------------------------------
# ユーティリティ
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    """UTC の現在時刻を ISO 8601 文字列で返す。"""
    return datetime.now(timezone.utc).isoformat()


def _sse(event: str, data: dict) -> str:
    """SSE フォーマット文字列を生成する。"""
    payload = json.dumps({"event": event, "data": data}, ensure_ascii=False)
    return f"data: {payload}\n\n"


# ---------------------------------------------------------------------------
# クエリ分析
# ---------------------------------------------------------------------------


async def analyze_query(
    query: str,
    user_id: str,
    db: AsyncSession,
    user_memories: list[str] | None = None,
) -> QueryAnalysis:
    """
    LLM を使用してクエリの意図を分類し、フィルタ条件を抽出する。

    処理ステップ:
      1. NFKC 正規化を適用する
      2. LLM で意図分類とフィルタ抽出を行う（ユーザーメモリも参照）

    Args:
        query: ユーザーの生クエリ文字列。
        user_id: ユーザー ID。
        db: 非同期データベースセッション。
        user_memories: ユーザーメモリのコンテンツリスト（None の場合はユーザー情報なし）。

    Returns:
        QueryAnalysis データクラスインスタンス。
    """
    # Step 1: NFKC 正規化
    normalized = normalize_query(query)

    # Step 2: ユーザー情報をプロンプトに組み込む
    user_context = ""
    if user_memories:
        memory_lines = "\n".join(f"- {m}" for m in user_memories)
        user_context = f"## このユーザーについて\n{memory_lines}"

    system_prompt = _INTENT_SYSTEM_PROMPT.format(user_context=user_context)

    # Step 3: LLM で意図分類
    prompt = f"クエリ: {normalized}"

    intent = "DOC_SEARCH"
    filters: dict = {"site_code": None, "line_code": None, "process_codes": []}

    try:
        response = await bedrock_client.generate_text(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=256,
            temperature=0.0,
        )
        parsed = json.loads(response.strip())
        intent = parsed.get("intent", "DOC_SEARCH")
        if intent not in {"DOC_SEARCH", "ORACLE_QUERY", "HYBRID"}:
            intent = "DOC_SEARCH"

        filters = {
            "site_code": parsed.get("site_code"),
            "line_code": parsed.get("line_code"),
            "process_codes": parsed.get("process_codes") or [],
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "クエリ意図分類に失敗しました（デフォルト DOC_SEARCH を使用）: %s", exc
        )

    return QueryAnalysis(
        intent=intent,
        normalized_query=normalized,
        translated_query=normalized,
        filters=filters,
    )


# ---------------------------------------------------------------------------
# ドキュメント検索
# ---------------------------------------------------------------------------


async def search_documents(
    query_analysis: QueryAnalysis,
    knowledge_base_id: str,
    user: User,
    db: AsyncSession,
) -> list[RagSearchResult]:
    """
    Qdrant を使用してドキュメントのベクトル検索を実行する。

    ユーザー設定に応じてハイブリッド検索とリランクを適用する。
    関連度スコアが RELEVANCE_THRESHOLD 未満のチャンクを除外する。
    子チャンクがヒットした場合は親チャンクへ展開してコンテキストを補完する。

    Args:
        query_analysis: analyze_query の結果。
        knowledge_base_id: 検索対象ナレッジベース ID。
        user: ユーザー ORM オブジェクト（設定フラグを参照）。
        db: 非同期データベースセッション（将来の親チャンク展開に使用）。

    Returns:
        RagSearchResult のリスト（スコア降順）。
    """
    import asyncio

    search_query = query_analysis.translated_query
    filters = query_analysis.filters

    expanded_queries = query_analysis.expanded_queries

    # 全クエリ（プライマリ + 拡張）を並列ベクトル化する（検索クエリ側の input_type）
    all_queries = [search_query] + expanded_queries
    query_vectors = await bedrock_client.embed_texts(
        all_queries, input_type="search_query"
    )

    # Qdrant フィルタを構築する
    qdrant_filter = qdrant_client.build_search_filter(
        knowledge_base_id=knowledge_base_id,
        site_code=filters.get("site_code"),
        line_code=filters.get("line_code"),
        process_codes=filters.get("process_codes") or None,
    )

    # 取得件数（ユーザー設定、デフォルト10）
    retrieval_limit = getattr(user, "retrieval_count", 10) or 10

    # 全クエリベクトルで並列 Qdrant 検索を実行する
    dense_search_tasks = [
        asyncio.to_thread(
            qdrant_client.search_vectors,
            collection=config.QDRANT_COLLECTION,
            query_vector=qv,
            limit=retrieval_limit,
            filters=qdrant_filter,
        )
        for qv in query_vectors
    ]
    all_dense_results = await asyncio.gather(*dense_search_tasks)

    # 複数クエリの結果を RRF で統合する
    if len(all_dense_results) > 1:
        raw_results = _fuse_multiple_results_rrf(list(all_dense_results), k=60)
        logger.info(
            "マルチクエリ検索: %d クエリ → RRF統合後 %d 件",
            len(all_dense_results),
            len(raw_results),
        )
    else:
        raw_results = all_dense_results[0]

    # ハイブリッド検索（スパースベクトル）— プライマリクエリのみ
    did_hybrid_fuse = False
    if user.hybrid_search_enabled:
        from app.services.embedder import generate_sparse_vector

        sparse_indices, sparse_values = generate_sparse_vector(search_query)
        if sparse_indices:
            dense_count = len(raw_results)
            sparse_results = await asyncio.to_thread(
                qdrant_client.search_sparse_vectors,
                collection=config.QDRANT_COLLECTION,
                sparse_indices=sparse_indices,
                sparse_values=sparse_values,
                limit=retrieval_limit,
                filters=qdrant_filter,
            )
            # RRF (Reciprocal Rank Fusion) で密・疎の結果をマージする
            raw_results = _fuse_results_rrf(raw_results, sparse_results, k=60)
            did_hybrid_fuse = True
            logger.info(
                "ハイブリッド検索: 密 %d 件 + 疎 %d 件 → RRF統合後 %d 件",
                dense_count,
                len(sparse_results),
                len(raw_results),
            )
        else:
            logger.info(
                "ハイブリッド検索: クエリから疎ベクトルを生成できず密検索のみ使用"
            )

    # リランク処理（有効な場合）
    if user.rerank_enabled and raw_results:
        documents = [r.payload.get("content", "") for r in raw_results]
        reranked = await bedrock_client.rerank(
            query=search_query,
            documents=documents,
            top_n=min(10, len(documents)),
        )
        # リランク結果でスコアを更新する
        reranked_results = []
        for rr in reranked:
            original = raw_results[rr.index]
            reranked_results.append(
                qdrant_client.SearchResult(
                    id=original.id,
                    score=rr.relevance_score,
                    payload=original.payload,
                )
            )
        raw_results = reranked_results

    # スコアフィルタリング
    # マルチクエリ RRF やハイブリッド RRF を通った結果のスコアは 1/(k+rank) スケールで
    # コサイン類似度の閾値（RELEVANCE_THRESHOLD）と比較できないため、上位 N 件で打ち切る。
    # 単一クエリ・dense のみの場合のみコサイン閾値フィルタを適用する。
    used_rrf = len(all_dense_results) > 1 or did_hybrid_fuse
    if used_rrf:
        filtered = raw_results[:retrieval_limit]
        logger.info(
            "ベクトル検索 (RRF統合): %d 件ヒット → 上位 %d 件を採用（コサイン閾値は適用せず）",
            len(raw_results),
            len(filtered),
        )
    else:
        threshold = config.RELEVANCE_THRESHOLD
        filtered = [r for r in raw_results if r.score >= threshold]
        logger.info(
            "ベクトル検索: %d 件ヒット → 閾値フィルタ後 %d 件 (threshold=%.2f)",
            len(raw_results),
            len(filtered),
            threshold,
        )

    # RagSearchResult に変換する
    results: list[RagSearchResult] = []
    for r in filtered:
        payload = r.payload
        # content を優先し、parent_content はコンテキスト補完として前置する
        chunk_content = payload.get("content", "")
        parent_content = payload.get("parent_content", "")
        if chunk_content and parent_content:
            content = f"{parent_content}\n\n{chunk_content}"
        else:
            content = chunk_content or parent_content
        results.append(
            RagSearchResult(
                content=content,
                document_id=payload.get("document_id", ""),
                document_name=payload.get("document_name", ""),
                section_title=payload.get("section_title", ""),
                score=r.score,
                chunk_id=r.id,
            )
        )

    return results


async def expand_query(query: str, count: int = 3) -> list[str]:
    """
    LLM を使用して元のクエリから代替クエリを生成する。

    表現の揺れやキーワードの言い換えによる検索漏れを防ぐため、
    異なる観点・表現で言い換えたクエリを生成する。

    Args:
        query: 元のクエリ文字列。
        count: 生成する代替クエリの数。

    Returns:
        代替クエリ文字列のリスト。エラー時は空リスト。
    """
    system_prompt = (
        "あなたは検索クエリの拡張を行うAIです。\n"
        "ユーザーの質問を異なる表現・観点で言い換えた検索クエリを生成してください。\n"
        "元の意味を保ちつつ、異なるキーワードや表現を使ってください。\n"
        f"必ず{count}件のクエリを改行区切りで出力してください。番号や記号は付けないでください。"
    )

    try:
        response = await bedrock_client.generate_text(
            prompt=f"元のクエリ: {query}",
            system_prompt=system_prompt,
            max_tokens=256,
            temperature=0.7,
        )
        lines = [line.strip() for line in response.strip().splitlines() if line.strip()]
        # 元クエリと同一のものは除外
        expanded = [line for line in lines if line != query][:count]
        logger.info("クエリ拡張: %d件の代替クエリを生成しました", len(expanded))
        return expanded
    except Exception as exc:  # noqa: BLE001
        logger.warning("クエリ拡張に失敗しました（元クエリのみで検索します）: %s", exc)
        return []


def _fuse_results_rrf(
    dense_results: list,
    sparse_results: list,
    k: int = 60,
) -> list:
    """
    Reciprocal Rank Fusion (RRF) で密ベクトルとスパースベクトルの検索結果を統合する。

    Args:
        dense_results: 密ベクトル検索結果リスト。
        sparse_results: スパースベクトル検索結果リスト。
        k: RRF ランク平滑化定数。

    Returns:
        統合・再ランク付けされた検索結果リスト。
    """
    scores: dict[str, float] = {}
    result_map: dict[str, object] = {}

    for rank, result in enumerate(dense_results, start=1):
        rid = result.id
        scores[rid] = scores.get(rid, 0.0) + 1.0 / (k + rank)
        result_map[rid] = result

    for rank, result in enumerate(sparse_results, start=1):
        rid = result.id
        scores[rid] = scores.get(rid, 0.0) + 1.0 / (k + rank)
        result_map[rid] = result

    sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
    fused = []
    for rid in sorted_ids:
        r = result_map[rid]
        # スコアを RRF スコアで上書きする
        fused.append(
            qdrant_client.SearchResult(
                id=r.id,
                score=scores[rid],
                payload=r.payload,
            )
        )
    return fused


def _fuse_multiple_results_rrf(
    result_lists: list[list],
    k: int = 60,
) -> list:
    """
    複数の検索結果リストを Reciprocal Rank Fusion (RRF) で統合する。

    _fuse_results_rrf の N リスト対応版。各リスト内のランクに基づいて
    RRF スコアを計算し、統合結果をスコア降順で返す。

    Args:
        result_lists: 検索結果リストのリスト。
        k: RRF ランク平滑化定数。

    Returns:
        統合・再ランク付けされた検索結果リスト。
    """
    scores: dict[str, float] = {}
    result_map: dict[str, object] = {}

    for results in result_lists:
        for rank, result in enumerate(results, start=1):
            rid = result.id
            scores[rid] = scores.get(rid, 0.0) + 1.0 / (k + rank)
            result_map[rid] = result

    sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
    fused = []
    for rid in sorted_ids:
        r = result_map[rid]
        fused.append(
            qdrant_client.SearchResult(
                id=r.id,
                score=scores[rid],
                payload=r.payload,
            )
        )
    return fused


# ---------------------------------------------------------------------------
# 回答生成ストリーム
# ---------------------------------------------------------------------------

_NO_RESULT_MESSAGE = (
    "選択されたナレッジベース内に該当する情報が見つかりませんでした。"
    "別のキーワードでお試しいただくか、管理者にお問い合わせください。"
)

_SYSTEM_PROMPT_TEMPLATE = """\
あなたは製造現場の知識ベースを活用する RAG アシスタントです。

## 厳守ルール
- 参照文書とユーザー情報（「このユーザーについて」セクション）を活用して回答してください。それ以外の一般知識は使用しないでください。
- ユーザー自身に関する質問（所属、担当ライン、ラインコード、拠点など）には「このユーザーについて」の情報から直接回答してください。この場合、参照文書は不要です。
- 参照文書にもユーザー情報にも記載されていない情報のみ「文書に記載がありません」と明示してください。ユーザー情報から回答できる場合は「文書に記載がありません」と言わないでください。
- 回答は日本語で行ってください。

## 回答スタイル
{response_mode_instruction}
{user_memory_section}"""

_RESPONSE_MODE_SIMPLE = """\
**必ず短く回答してください。**
- 箇条書き3〜5項目以内で要点のみを述べてください
- 各項目は1〜2文に収めてください
- 補足説明・背景・引用は省略してください
- 回答全体を200文字以内に抑えてください"""

_RESPONSE_MODE_DETAILED = """\
詳細かつ丁寧に回答してください。
- 段落形式で背景・原因・対処法を網羅的に説明してください
- 根拠となる文書箇所を「出典: 〇〇」の形式で引用してください
- 必要に応じてステップバイステップの手順を含めてください"""


def _build_system_prompt(
    response_mode: str, user_memories: list[str] | None = None
) -> str:
    """
    ユーザーの回答モードとメモリ情報に応じたシステムプロンプトを構築する。

    Args:
        response_mode: "simple" または "detailed"。
        user_memories: ユーザーメモリのコンテンツリスト（任意）。

    Returns:
        システムプロンプト文字列。
    """
    instruction = (
        _RESPONSE_MODE_DETAILED
        if response_mode == "detailed"
        else _RESPONSE_MODE_SIMPLE
    )

    memory_section = ""
    if user_memories:
        memory_lines = "\n".join(f"- {m}" for m in user_memories)
        memory_section = f"""
## このユーザーについて
以下はユーザーが登録した自分に関する情報です。回答時にこのコンテキストを考慮してください。
{memory_lines}
"""

    return _SYSTEM_PROMPT_TEMPLATE.format(
        response_mode_instruction=instruction,
        user_memory_section=memory_section,
    )


def _build_user_prompt(
    query: str,
    search_results: list[RagSearchResult],
    oracle_result: OracleQueryResult | None,
) -> str:
    """
    検索コンテキストと Oracle データを組み合わせたユーザープロンプトを構築する。

    Args:
        query: ユーザーの質問文字列。
        search_results: ドキュメント検索結果リスト。
        oracle_result: Oracle クエリ結果（None の場合はスキップ）。

    Returns:
        プロンプト文字列。
    """
    parts: list[str] = []

    if search_results:
        parts.append("## 参照文書\n")
        for i, result in enumerate(search_results, start=1):
            title = result.section_title or result.document_name or f"文書{i}"
            parts.append(f"### [{i}] {title} (関連度: {result.score:.2f})")
            parts.append(result.content)
            parts.append("")

    if oracle_result is not None and oracle_result.row_count > 0:
        parts.append("## データベースクエリ結果\n")
        header = " | ".join(oracle_result.columns)
        separator = " | ".join(["---"] * len(oracle_result.columns))
        parts.append(f"| {header} |")
        parts.append(f"| {separator} |")
        for row in oracle_result.rows:
            row_str = " | ".join(str(v) if v is not None else "-" for v in row)
            parts.append(f"| {row_str} |")
        if oracle_result.truncated:
            parts.append(
                f"\n*注: {config.ORACLE_ROW_LIMIT} 行を超えたため結果を切り詰めました*"
            )
        parts.append("")

    context_text = "\n".join(parts) if parts else ""

    prompt_parts = []
    if context_text:
        prompt_parts.append(context_text)
    prompt_parts.append(f"## 質問\n{query}")

    return "\n".join(prompt_parts)


async def generate_answer_stream(
    query: str,
    search_results: list[RagSearchResult],
    oracle_result: OracleQueryResult | None,
    user: User,
    session_id: str,
    knowledge_base_id: str,
    db: AsyncSession,
    user_memories: list[str] | None = None,
) -> AsyncGenerator[str, None]:
    """
    RAG コンテキストを使用してストリーミング回答を生成し、SSE イベントを yield する。

    イベント順序: session → status → token(複数) → sources → output → complete → done

    生成完了後、ユーザーメッセージとアシスタントメッセージを DB に保存する。

    Args:
        query: ユーザーの質問文字列。
        search_results: search_documents の結果リスト。
        oracle_result: process_oracle_query の結果（None の場合はスキップ）。
        user: ユーザー ORM オブジェクト。
        session_id: 会話セッション ID。
        knowledge_base_id: 対象ナレッジベース ID。
        db: 非同期データベースセッション。
        user_memories: ユーザーメモリのコンテンツリスト（None の場合は内部で取得）。

    Yields:
        SSE フォーマット文字列（`data: {...}\\n\\n`）。
    """
    has_results = bool(search_results) or (
        oracle_result is not None and oracle_result.row_count > 0
    )

    # セッションイベント
    yield _sse(
        "session", {"session_id": session_id, "knowledge_base_id": knowledge_base_id}
    )

    # ステータスイベント
    yield _sse("status", {"message": "回答を生成しています...", "stage": "generating"})

    # 結果がなく、メモリもない場合のみ固定メッセージを返す
    if not has_results and not user_memories:
        yield _sse("token", {"text": _NO_RESULT_MESSAGE})

        # DB 保存
        assistant_message_id = await _save_messages(
            query=query,
            answer=_NO_RESULT_MESSAGE,
            search_results=[],
            session_id=session_id,
            user=user,
            db=db,
        )

        yield _sse("sources", {"items": []})
        yield _sse("output", {"type": "none", "message_id": assistant_message_id})
        yield _sse(
            "complete",
            {
                "status": "ok",
                "message_id": assistant_message_id,
                "full_answer": _NO_RESULT_MESSAGE,
            },
        )
        yield _sse("done", {})
        return

    # ユーザーメモリを取得してプロンプトに注入する（呼び出し元で取得済みの場合はスキップ）
    if user_memories is None:
        memory_result = await db.execute(
            select(UserMemory.content)
            .where(UserMemory.user_id == user.id)
            .order_by(UserMemory.created_at)
        )
        user_memories = [row[0] for row in memory_result.all()]

    # プロンプト構築
    system_prompt = _build_system_prompt(user.response_mode, user_memories)
    user_prompt = _build_user_prompt(query, search_results, oracle_result)

    # ストリーミングでトークンを yield する
    full_answer_parts: list[str] = []

    try:
        async for token in bedrock_client.generate_text_stream(
            prompt=user_prompt,
            system_prompt=system_prompt,
            max_tokens=512 if user.response_mode == "simple" else 4096,
            temperature=0.3,
        ):
            full_answer_parts.append(token)
            yield _sse("token", {"text": token})
    except Exception as exc:
        logger.error("テキスト生成中にエラーが発生しました: %s", exc)
        error_msg = (
            "回答の生成中にエラーが発生しました。しばらく後に再試行してください。"
        )
        yield _sse("token", {"text": error_msg})
        full_answer_parts = [error_msg]

    full_answer = "".join(full_answer_parts)

    # ソース情報を構築する（document_name が空の場合は DB から filename を補完する）
    doc_ids = {
        r.document_id for r in search_results if r.document_id and not r.document_name
    }
    doc_name_map: dict[str, str] = {}
    if doc_ids:
        from app.models.database import Document as DocModel

        result = await db.execute(
            select(DocModel.id, DocModel.filename).where(DocModel.id.in_(doc_ids))
        )
        for row in result:
            doc_name_map[row.id] = row.filename

    sources_items = [
        {
            "chunk_id": r.chunk_id,
            "document_id": r.document_id,
            "document_name": r.document_name or doc_name_map.get(r.document_id, ""),
            "section_title": r.section_title,
            "score": round(r.score, 3),
            "snippet": r.content[:300] if r.content else "",
        }
        for r in search_results
    ]
    yield _sse("sources", {"items": sources_items})

    # DB 保存（アシスタントメッセージ ID を取得する）
    sources_json = json.dumps(sources_items, ensure_ascii=False)
    assistant_message_id = await _save_messages(
        query=query,
        answer=full_answer,
        search_results=search_results,
        session_id=session_id,
        user=user,
        db=db,
        sources_json=sources_json,
    )

    # Oracle 出力情報を構造化して保存し SSE を送信する
    if oracle_result is not None and oracle_result.row_count > 0:
        table_data = format_table_data(oracle_result.columns, oracle_result.rows)
        chart_config = suggest_chart_config(table_data, query)

        # output_type を決定する
        if chart_config is not None:
            output_type = "both"
        else:
            output_type = "table"

        # chat_outputs テーブルに保存する
        try:
            await save_output(
                db=db,
                message_id=assistant_message_id,
                output_type=output_type,
                table_data=table_data,
                chart_config=chart_config,
                sql_executed=oracle_result.sql_executed or None,
                row_count=oracle_result.row_count,
            )
        except Exception as exc:
            logger.error("ChatOutput の保存に失敗しました: %s", exc)

        yield _sse(
            "output",
            {
                "type": output_type,
                "message_id": assistant_message_id,
                "table_data": table_data,
                "chart_config": chart_config,
                "row_count": oracle_result.row_count,
                "truncated": oracle_result.truncated,
            },
        )
    else:
        yield _sse("output", {"type": "none", "message_id": assistant_message_id})

    yield _sse(
        "complete",
        {
            "status": "ok",
            "message_id": assistant_message_id,
            "full_answer": full_answer,
        },
    )
    yield _sse("done", {})


async def _save_messages(
    query: str,
    answer: str,
    search_results: list[RagSearchResult],
    session_id: str,
    user: User,
    db: AsyncSession,
    sources_json: str | None = None,
) -> str:
    """
    ユーザーメッセージとアシスタントメッセージを DB に保存し、セッションを更新する。

    Args:
        query: ユーザーの入力テキスト。
        answer: アシスタントの回答テキスト。
        search_results: 参照された検索結果リスト。
        session_id: セッション ID。
        user: ユーザー ORM オブジェクト。
        db: 非同期データベースセッション。
        sources_json: ソース情報の JSON 文字列（None の場合はスキップ）。

    Returns:
        保存したアシスタントメッセージの ID 文字列。
    """
    now = _now_iso()

    # ユーザーメッセージを保存する
    user_msg = Message(
        id=str(uuid.uuid4()),
        session_id=session_id,
        role="user",
        content=query,
        input_type="text",
        response_mode=user.response_mode,
        is_cancelled=0,
        created_at=now,
    )
    db.add(user_msg)

    # アシスタントメッセージを保存する
    assistant_message_id = str(uuid.uuid4())
    assistant_msg = Message(
        id=assistant_message_id,
        session_id=session_id,
        role="assistant",
        content=answer,
        sources=sources_json,
        input_type="text",
        response_mode=user.response_mode,
        is_cancelled=0,
        created_at=now,
    )
    db.add(assistant_msg)

    # セッションの updated_at を更新する
    session_result = await db.execute(select(Session).where(Session.id == session_id))
    session = session_result.scalar_one_or_none()
    if session is not None:
        session.updated_at = now

    try:
        await db.commit()
    except Exception as exc:
        logger.error("メッセージの DB 保存に失敗しました: %s", exc)

    return assistant_message_id


# ---------------------------------------------------------------------------
# メインオーケストレーター
# ---------------------------------------------------------------------------


async def run_rag_pipeline(
    query: str,
    session_id: str,
    knowledge_base_id: str,
    user_id: str,
    db: AsyncSession,
) -> AsyncGenerator[str, None]:
    """
    RAG パイプラインを実行し、SSE イベントをストリーミングで生成する。

    処理ステップ:
      1. クエリを分析して意図・フィルタ・用語変換を取得する
      2. ステータス SSE を yield する
      3a. 意図が DOC_SEARCH または HYBRID の場合: ドキュメント検索を実行する
      3b. 意図が ORACLE_QUERY または HYBRID の場合: Oracle クエリを実行する
      4. LLM でストリーミング回答を生成する
      5. 全 SSE イベントを yield する

    エラーが発生した場合は error SSE イベントを yield して終了する。

    Args:
        query: ユーザーの入力クエリ文字列。
        session_id: 会話セッション ID。
        knowledge_base_id: 検索対象ナレッジベース ID。
        user_id: ユーザー ID。
        db: 非同期データベースセッション。

    Yields:
        SSE フォーマット文字列（`data: {...}\\n\\n`）。
    """
    # ユーザーを取得する（設定フラグ参照のため）
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()

    if user is None:
        # ユーザーが存在しない場合はデフォルト設定で続行する
        logger.warning("ユーザーが見つかりません: user_id=%s", user_id)
        user = User(
            id=user_id,
            rerank_enabled=0,
            hybrid_search_enabled=1,
            retrieval_count=20,
            response_mode="detailed",
            search_mode="normal",
            created_at=_now_iso(),
            updated_at=_now_iso(),
        )

    # ユーザーメモリを早期に取得（検索結果なしでもメモリで回答可能か判断するため）
    memory_result = await db.execute(
        select(UserMemory.content)
        .where(UserMemory.user_id == user.id)
        .order_by(UserMemory.created_at)
    )
    user_memories = [row[0] for row in memory_result.all()]

    try:
        # Step 1: クエリ分析
        yield _sse(
            "status", {"message": "クエリを分析しています...", "stage": "analyzing"}
        )

        query_analysis = await analyze_query(query, user_id, db, user_memories)
        logger.info(
            "クエリ分析完了: intent=%s, query=%r",
            query_analysis.intent,
            query_analysis.translated_query,
        )

        # Step 1.5: クエリ拡張（DOC_SEARCH / HYBRID の場合のみ）
        if query_analysis.intent in {"DOC_SEARCH", "HYBRID"}:
            expanded = await expand_query(
                query_analysis.translated_query,
                count=config.QUERY_EXPANSION_COUNT,
            )
            query_analysis.expanded_queries = expanded

        # Step 2: ステータス通知
        yield _sse(
            "status",
            {
                "message": "情報を検索しています...",
                "stage": "searching",
                "intent": query_analysis.intent,
            },
        )

        search_results: list[RagSearchResult] = []
        oracle_result: OracleQueryResult | None = None

        # Step 3a: ドキュメント検索
        if query_analysis.intent in {"DOC_SEARCH", "HYBRID"}:
            try:
                search_results = await search_documents(
                    query_analysis=query_analysis,
                    knowledge_base_id=knowledge_base_id,
                    user=user,
                    db=db,
                )
                logger.info("ドキュメント検索完了: %d 件", len(search_results))
            except Exception as exc:
                logger.error("ドキュメント検索中にエラーが発生しました: %s", exc)
                yield _sse(
                    "status",
                    {
                        "message": "ドキュメント検索でエラーが発生しました",
                        "stage": "error",
                    },
                )

        # Step 3b: Oracle クエリ
        if query_analysis.intent in {"ORACLE_QUERY", "HYBRID"}:
            yield _sse(
                "status",
                {"message": "データベースを照会しています...", "stage": "oracle"},
            )
            try:
                oracle_result = await process_oracle_query(
                    query=query_analysis.translated_query,
                    db=db,
                )
                logger.info("Oracle クエリ完了: %d 行", oracle_result.row_count)
            except OracleUnavailableError as exc:
                logger.warning("Oracle が利用不可です: %s", exc)
                yield _sse(
                    "status",
                    {
                        "message": "データベースは現在利用できません（ドキュメント検索のみで回答します）",
                        "stage": "oracle_unavailable",
                    },
                )
            except Exception as exc:
                logger.error("Oracle クエリ中にエラーが発生しました: %s", exc)
                yield _sse(
                    "status",
                    {
                        "message": "データベースクエリでエラーが発生しました",
                        "stage": "error",
                    },
                )

        # Step 4 & 5: 回答生成ストリーム
        async for event in generate_answer_stream(
            query=query,
            search_results=search_results,
            oracle_result=oracle_result,
            user=user,
            session_id=session_id,
            knowledge_base_id=knowledge_base_id,
            db=db,
            user_memories=user_memories,
        ):
            yield event

    except Exception as exc:
        logger.exception("RAG パイプラインで予期しないエラーが発生しました: %s", exc)
        yield _sse(
            "error",
            {
                "message": "内部エラーが発生しました。しばらく後に再試行してください。",
                "detail": str(exc),
            },
        )
        yield _sse("done", {})


# ---------------------------------------------------------------------------
# エージェンティックサーチ
# ---------------------------------------------------------------------------

_AGENTIC_LIST_DOCUMENTS_TOOL: dict[str, object] = {
    "name": "list_documents",
    "description": (
        "ナレッジベース内のドキュメント一覧を取得する。"
        "各ドキュメントの ID・ファイル名・文字数が返される。"
        "まずこのツールで一覧を確認してから search_in_document や "
        "read_document_section で内容を調査すること。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {},
    },
}

_AGENTIC_SEARCH_IN_DOCUMENT_TOOL: dict[str, object] = {
    "name": "search_in_document",
    "description": (
        "ドキュメント本文内をキーワード検索する。"
        "スペース区切りで複数キーワードを指定すると AND 検索になる。"
        "マッチした行と前後のコンテキスト、文字オフセットを返す。"
        "大きなドキュメントでは、まずこのツールで関連箇所を特定してから "
        "read_document_section で詳しく読むのが効率的。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "document_id": {
                "type": "string",
                "description": "検索するドキュメントの ID（list_documents で取得）",
            },
            "query": {
                "type": "string",
                "description": "検索キーワード（スペース区切りで AND 検索）",
            },
            "max_results": {
                "type": "integer",
                "description": "最大結果数（デフォルト: 10）",
                "default": 10,
            },
        },
        "required": ["document_id", "query"],
    },
}

_AGENTIC_READ_DOCUMENT_SECTION_TOOL: dict[str, object] = {
    "name": "read_document_section",
    "description": (
        "ドキュメントの指定範囲を読み込む。"
        "offset と length で読み込む範囲を指定する。"
        "search_in_document の char_offset を使って関連箇所にジャンプできる。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "document_id": {
                "type": "string",
                "description": "読み込むドキュメントの ID（list_documents で取得）",
            },
            "offset": {
                "type": "integer",
                "description": "読み込み開始位置（文字数、デフォルト: 0）",
                "default": 0,
            },
            "length": {
                "type": "integer",
                "description": "読み込む文字数（デフォルト: 10000、最大: 30000）",
                "default": 10000,
            },
        },
        "required": ["document_id"],
    },
}

_AGENTIC_BASE_TOOLS: list[dict[str, object]] = [
    _AGENTIC_LIST_DOCUMENTS_TOOL,
    _AGENTIC_SEARCH_IN_DOCUMENT_TOOL,
    _AGENTIC_READ_DOCUMENT_SECTION_TOOL,
]

_AGENTIC_QUERY_CSV_DATA_TOOL: dict[str, object] = {
    "name": "query_csv_data",
    "description": (
        "データ型フォルダソース内の CSV/TSV に対して SQL クエリを実行する。"
        "mode='describe' でテーブル一覧・カラム情報・サンプル行を取得し、"
        "mode='query' で SQL を実行して結果を取得する。"
        "まず describe でスキーマを確認してから query を実行すること。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "source_id": {
                "type": "string",
                "description": "データ型フォルダソースの ID（list_documents で取得）",
            },
            "mode": {
                "type": "string",
                "enum": ["describe", "query"],
                "description": "describe: テーブル情報取得、query: SQL 実行",
            },
            "sql_query": {
                "type": "string",
                "description": "実行する SQL クエリ（mode=query のとき必須、SELECT/WITH のみ）",
            },
        },
        "required": ["source_id", "mode"],
    },
}

_AGENTIC_SYSTEM_PROMPT_TEMPLATE = """\
あなたは製造現場の知識ベースを活用する RAG アシスタントです。

## 行動指針
1. まず list_documents でナレッジベース内のドキュメント一覧を確認してください。
2. search_in_document でキーワード検索し、関連する箇所を特定してください。
3. 見つかった箇所を read_document_section で詳しく読み込んでください。
4. 情報が不足する場合は、別のキーワードで再検索するか、別のドキュメントを検索してください。
5. 最大{max_iterations}回までツールを使用できます。

## 検索のコツ
- search_in_document はスペース区切りで AND 検索できる。「モータ 43」のように複数キーワードを組み合わせて絞り込むこと
- **複合キーワードで 0 件または部分一致のみの場合は、キーワードを減らして再検索する**。例:「K298 エア圧力 規格値」→0件なら「エア圧力 規格」「K298」のように分割して個別に検索し、結果を突き合わせる
- 検索結果に "match_type": "partial" が含まれる場合、全キーワードが近くに見つからなかったことを意味する。その場合はキーワードを絞って再検索すること
- 見つからない場合は同義語や表記ゆれで再検索する
- 大きなドキュメントは search_in_document で場所を特定してから read_document_section で読む
{data_source_section}
## 回答ルール
- ドキュメントの原文に基づいて回答してください。一般知識は使用しないでください。
- 情報源のドキュメント名を明示してください。
- 回答は日本語で行ってください。

## 回答スタイル
{response_mode_instruction}
{user_memory_section}"""

_DATA_SOURCE_SECTION = """
## データソースの使い方
list_documents で「[データ: ...]」と表示されるエントリは CSV/TSV データソースです。
これらのデータに対しては query_csv_data ツールを使ってください。

1. まず mode="describe" でテーブル一覧・カラム名・サンプルデータを確認する
2. テーブル構造を把握してから mode="query" で SQL を生成・実行する
3. SQL は SELECT/WITH のみ使用可能。テーブル名はdescribeで返されたものを使う
4. 集計・フィルタリング・結合などの分析クエリを積極的に使い、必要なデータを抽出する
5. 結果が多い場合は LIMIT を付けること
"""


def _is_folder_doc(document_id: str) -> bool:
    """virtual document ID がフォルダソース由来か判定する。"""
    return document_id.startswith("folder:")


def _parse_folder_doc_id(document_id: str) -> tuple[str, str]:
    """virtual document ID を (source_id, relative_path) に分解する。"""
    # folder:{source_id}:{relative_path}
    parts = document_id.split(":", 2)
    if len(parts) < 3:
        return ("", "")
    return (parts[1], parts[2])


async def _get_folder_doc_content(
    document_id: str,
    db: AsyncSession,
    cache: dict[str, str],
) -> tuple[str, str]:
    """
    フォルダファイルのテキスト内容を取得する（キャッシュ付き）。

    Returns:
        (filename, text_content) のタプル。
    """
    if document_id in cache:
        source_id, rel_path = _parse_folder_doc_id(document_id)
        return (
            rel_path.rsplit("/", 1)[-1] if "/" in rel_path else rel_path,
            cache[document_id],
        )

    source_id, rel_path = _parse_folder_doc_id(document_id)
    if not source_id or not rel_path:
        return ("", "")

    from app.models.database import FolderSource

    result = await db.execute(select(FolderSource).where(FolderSource.id == source_id))
    source = result.scalar_one_or_none()
    if source is None:
        return ("", "")

    import os

    abs_path = os.path.join(source.container_path, rel_path)
    # パストラバーサル防止
    real_abs = os.path.realpath(abs_path)
    real_base = os.path.realpath(source.container_path)
    if not real_abs.startswith(real_base + os.sep) and real_abs != real_base:
        logger.warning("パストラバーサル検出: %s (base: %s)", real_abs, real_base)
        return ("", "")

    filename = rel_path.rsplit("/", 1)[-1] if "/" in rel_path else rel_path

    try:
        from app.services.converter import convert_file

        conversion = await convert_file(abs_path, filename)
        text = conversion.markdown
    except Exception as exc:
        logger.warning("フォルダファイル変換失敗: %s: %s", abs_path, exc)
        text = f"[読み取り失敗: {exc}]"

    cache[document_id] = text
    return (filename, text)


async def _list_kb_documents(
    knowledge_base_id: str,
    db: AsyncSession,
) -> list[dict[str, object]]:
    """ナレッジベース内のドキュメント一覧（ID・ファイル名・文字数）を返す。"""
    from app.models.database import Document as DocModel, FolderSource
    from app.services.folder_scanner import scan_folder
    from sqlalchemy import func

    result = await db.execute(
        select(
            DocModel.id,
            DocModel.filename,
            DocModel.file_type,
            func.length(DocModel.converted_md).label("char_count"),
        )
        .where(
            DocModel.knowledge_base_id == knowledge_base_id,
            DocModel.deleted_at.is_(None),
            DocModel.converted_md.isnot(None),
        )
        .order_by(DocModel.filename)
    )
    docs: list[dict[str, object]] = [
        {
            "id": row.id,
            "filename": row.filename,
            "file_type": row.file_type,
            "char_count": row.char_count or 0,
        }
        for row in result
    ]

    # フォルダソースからの仮想ドキュメントを追加
    fs_result = await db.execute(
        select(FolderSource).where(FolderSource.knowledge_base_id == knowledge_base_id)
    )
    folder_sources = fs_result.scalars().all()
    for source in folder_sources:
        label = source.label or "Folder"

        # データ型: CSV テーブル数のみ簡潔に表示（describe は query_csv_data ツールで実行）
        if source.source_type == "data":
            from app.services.duckdb_query import _find_csv_files

            csv_files = _find_csv_files(source.container_path)
            if csv_files:
                preview_names = ", ".join(name for _, name in csv_files[:5])
                suffix = f", 他{len(csv_files) - 5}件" if len(csv_files) > 5 else ""
                docs.append(
                    {
                        "id": f"datasource:{source.id}",
                        "filename": f"[データ: {label}] CSV {len(csv_files)}テーブル ({preview_names}{suffix})",
                        "file_type": "csv-data",
                        "char_count": 0,
                    }
                )
            continue

        # ドキュメント型: 個別ファイル列挙
        try:
            scanned = scan_folder(
                source.container_path,
                max_files=config.FOLDER_SOURCE_MAX_FILES,
            )
        except Exception as exc:
            logger.warning("フォルダスキャン失敗 (%s): %s", source.container_path, exc)
            continue
        for f in scanned:
            import os

            _, ext = os.path.splitext(f.filename)
            docs.append(
                {
                    "id": f"folder:{source.id}:{f.relative_path}",
                    "filename": f"[{label}] {f.relative_path}",
                    "file_type": ext.lstrip(".").lower(),
                    "char_count": f.size_bytes,
                }
            )

    return docs


def _keyword_search_in_text(
    content: str,
    query: str,
    max_results: int = 10,
    context_lines: int = 3,
    window_size: int = 20,
) -> list[dict[str, object]]:
    """テキスト内をキーワード検索し、マッチ行と前後コンテキストを返す共通ロジック。

    検索戦略:
    1. スライディングウィンドウ AND 検索: window_size 行の範囲内に
       すべてのキーワードが存在する箇所をマッチとして返す。
    2. OR フォールバック: AND で 0 件の場合、いずれかのキーワードを含む行を
       マッチキーワード数の降順で返す（LLM に手がかりを提供）。
    """
    keywords = [kw.lower() for kw in query.split() if kw.strip()]
    if not keywords:
        return []

    lines = content.split("\n")

    line_offsets: list[int] = []
    offset = 0
    for line in lines:
        line_offsets.append(offset)
        offset += len(line) + 1

    # --- Phase 1: スライディングウィンドウ AND 検索 ---
    matches: list[dict[str, object]] = []

    if len(keywords) == 1:
        # 単一キーワードは従来どおり行単位
        kw = keywords[0]
        for i, line in enumerate(lines):
            if kw in line.lower():
                start = max(0, i - context_lines)
                end = min(len(lines), i + context_lines + 1)
                matches.append(
                    {
                        "line_number": i + 1,
                        "content": "\n".join(lines[start:end]),
                        "char_offset": line_offsets[i],
                    }
                )
                if len(matches) >= max_results:
                    break
        return matches

    # 各行に含まれるキーワードを事前計算
    line_kw_sets: list[set[str]] = []
    for line in lines:
        ll = line.lower()
        line_kw_sets.append({kw for kw in keywords if kw in ll})

    # ウィンドウ内の全キーワードが揃う箇所を検索
    used_lines: set[int] = set()
    for i in range(len(lines)):
        if i in used_lines:
            continue
        w_end = min(len(lines), i + window_size)
        window_kws: set[str] = set()
        for j in range(i, w_end):
            window_kws |= line_kw_sets[j]
        if len(window_kws) < len(keywords):
            continue
        # ウィンドウ内でキーワードが揃った — 最も多くのキーワードを含む行を中心に
        best_j = i
        best_count = 0
        for j in range(i, w_end):
            cnt = len(line_kw_sets[j])
            if cnt > best_count:
                best_count = cnt
                best_j = j
        start = max(0, best_j - context_lines)
        end = min(len(lines), best_j + context_lines + 1)
        matches.append(
            {
                "line_number": best_j + 1,
                "content": "\n".join(lines[start:end]),
                "char_offset": line_offsets[best_j],
            }
        )
        # このウィンドウ範囲を使用済みにして重複回避
        for j in range(i, w_end):
            used_lines.add(j)
        if len(matches) >= max_results:
            break

    if matches:
        return matches

    # --- Phase 2: OR フォールバック ---
    or_candidates: list[tuple[int, int, dict[str, object]]] = []
    for i, kw_set in enumerate(line_kw_sets):
        if not kw_set:
            continue
        start = max(0, i - context_lines)
        end = min(len(lines), i + context_lines + 1)
        or_candidates.append(
            (
                len(kw_set),
                i,
                {
                    "line_number": i + 1,
                    "content": "\n".join(lines[start:end]),
                    "char_offset": line_offsets[i],
                    "matched_keywords": sorted(kw_set),
                    "match_type": "partial",
                },
            )
        )
    # マッチキーワード数で降順ソート
    or_candidates.sort(key=lambda x: (-x[0], x[1]))
    return [c[2] for c in or_candidates[:max_results]]


async def _search_in_document(
    document_id: str,
    query: str,
    db: AsyncSession,
    max_results: int = 10,
    context_lines: int = 3,
    folder_cache: dict[str, str] | None = None,
) -> tuple[str, list[dict[str, object]]]:
    """
    ドキュメント本文内をキーワード検索し、マッチ行と前後コンテキストを返す。

    Returns:
        (filename, matches) のタプル。matches は
        [{"line_number", "content", "char_offset"}] のリスト。
    """
    # フォルダソースの場合
    if _is_folder_doc(document_id):
        if folder_cache is None:
            folder_cache = {}
        filename, content = await _get_folder_doc_content(document_id, db, folder_cache)
        if not content:
            return (filename, [])
        matches = _keyword_search_in_text(content, query, max_results, context_lines)
        return (filename, matches)

    from app.models.database import Document as DocModel

    result = await db.execute(
        select(DocModel.filename, DocModel.converted_md).where(
            DocModel.id == document_id
        )
    )
    row = result.one_or_none()
    if row is None:
        return ("", [])

    content = row.converted_md or ""
    if not content:
        return (row.filename or "", [])

    matches = _keyword_search_in_text(content, query, max_results, context_lines)
    return (row.filename or "", matches)


async def _read_document_section(
    document_id: str,
    db: AsyncSession,
    offset: int = 0,
    length: int = 10000,
    folder_cache: dict[str, str] | None = None,
) -> tuple[str, str, int, bool]:
    """
    ドキュメントの指定範囲を読み込む。

    Returns:
        (filename, content, total_chars, has_more) のタプル。
    """
    length = min(length, 30000)
    offset = max(offset, 0)

    # フォルダソースの場合
    if _is_folder_doc(document_id):
        if folder_cache is None:
            folder_cache = {}
        filename, full_content = await _get_folder_doc_content(
            document_id, db, folder_cache
        )
        total_chars = len(full_content)
        section = full_content[offset : offset + length]
        has_more = (offset + length) < total_chars
        return (filename, section, total_chars, has_more)

    from app.models.database import Document as DocModel

    result = await db.execute(
        select(DocModel.filename, DocModel.converted_md).where(
            DocModel.id == document_id
        )
    )
    row = result.one_or_none()
    if row is None:
        return ("", "", 0, False)

    full_content = row.converted_md or ""
    total_chars = len(full_content)
    section = full_content[offset : offset + length]
    has_more = (offset + length) < total_chars

    return (row.filename or "", section, total_chars, has_more)


async def run_agentic_search_pipeline(
    query: str,
    session_id: str,
    knowledge_base_id: str,
    user_id: str,
    db: AsyncSession,
) -> AsyncGenerator[str, None]:
    """
    エージェンティック検索パイプラインを実行し、SSE イベントをストリーミングで生成する。

    Claude がツール（search_knowledge_base）を反復的に使用して情報を収集し、
    十分な情報が得られたら最終回答を生成する。

    Args:
        query: ユーザーの入力クエリ文字列。
        session_id: 会話セッション ID。
        knowledge_base_id: 検索対象ナレッジベース ID。
        user_id: ユーザー ID。
        db: 非同期データベースセッション。

    Yields:
        SSE フォーマット文字列。
    """
    # ユーザーを取得
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()

    if user is None:
        logger.warning("ユーザーが見つかりません: user_id=%s", user_id)
        user = User(
            id=user_id,
            rerank_enabled=0,
            hybrid_search_enabled=1,
            retrieval_count=20,
            response_mode="detailed",
            search_mode="agentic",
            agentic_max_iterations=config.AGENTIC_MAX_ITERATIONS,
            created_at=_now_iso(),
            updated_at=_now_iso(),
        )

    # ユーザーメモリを取得
    memory_result = await db.execute(
        select(UserMemory.content)
        .where(UserMemory.user_id == user.id)
        .order_by(UserMemory.created_at)
    )
    user_memories = [row[0] for row in memory_result.all()]

    # ユーザー設定を優先し、未設定時はデフォルト値にフォールバック
    max_iterations = (
        getattr(user, "agentic_max_iterations", None) or config.AGENTIC_MAX_ITERATIONS
    )

    # セッション内で DuckDB 接続を再利用するためのキャッシュ。
    # finally でクリーンアップするため、try より前に初期化しておく
    # （try 内の早期例外で UnboundLocalError になるのを防ぐ）。
    csv_sessions: dict[str, "CsvDataSession"] = {}

    try:
        # セッションイベント
        yield _sse(
            "session",
            {"session_id": session_id, "knowledge_base_id": knowledge_base_id},
        )

        # システムプロンプト構築
        instruction = (
            _RESPONSE_MODE_DETAILED
            if user.response_mode == "detailed"
            else _RESPONSE_MODE_SIMPLE
        )
        memory_section = ""
        if user_memories:
            memory_lines = "\n".join(f"- {m}" for m in user_memories)
            memory_section = (
                f"\n## このユーザーについて\n"
                f"以下はユーザーが登録した自分に関する情報です。回答時にこのコンテキストを考慮してください。\n"
                f"{memory_lines}\n"
            )

        # データ型フォルダソースの有無を確認し、ツールリストを動的構築
        from app.models.database import FolderSource as FSModel

        fs_check = await db.execute(
            select(FSModel).where(
                FSModel.knowledge_base_id == knowledge_base_id,
                FSModel.source_type == "data",
            )
        )
        has_data_sources = fs_check.scalars().first() is not None
        # データソース ID→container_path マッピング（ツールハンドラ用）
        data_source_paths: dict[str, str] = {}
        if has_data_sources:
            fs_all = await db.execute(
                select(FSModel).where(
                    FSModel.knowledge_base_id == knowledge_base_id,
                    FSModel.source_type == "data",
                )
            )
            for fs in fs_all.scalars().all():
                data_source_paths[fs.id] = fs.container_path

        agentic_tools: list[dict[str, object]] = list(_AGENTIC_BASE_TOOLS)
        if has_data_sources:
            agentic_tools.append(_AGENTIC_QUERY_CSV_DATA_TOOL)

        data_source_section = _DATA_SOURCE_SECTION if has_data_sources else ""

        system_prompt = _AGENTIC_SYSTEM_PROMPT_TEMPLATE.format(
            max_iterations=max_iterations,
            response_mode_instruction=instruction,
            user_memory_section=memory_section,
            data_source_section=data_source_section,
        )

        # メッセージリスト初期化
        messages: list[dict[str, object]] = [
            {"role": "user", "content": [{"type": "text", "text": query}]},
        ]

        # 読み込んだドキュメントを追跡
        read_documents: dict[
            str, tuple[str, str]
        ] = {}  # {document_id: (filename, snippet)}
        folder_cache: dict[str, str] = {}  # {virtual_doc_id: text_content}
        final_text = ""

        # エージェンティックループ（反復回数 + 経過時間の二重ガード）
        loop_deadline = time.monotonic() + config.AGENTIC_LOOP_TIMEOUT
        for iteration in range(1, max_iterations + 1):
            if time.monotonic() > loop_deadline:
                logger.warning(
                    "エージェンティックループが時間制限 (%ds) を超えたため打ち切ります "
                    "(iteration=%d/%d)",
                    config.AGENTIC_LOOP_TIMEOUT,
                    iteration,
                    max_iterations,
                )
                break

            # thinking ステップ
            yield _sse(
                "agentic_step",
                {
                    "iteration": iteration,
                    "max_iterations": max_iterations,
                    "status": "thinking",
                },
            )

            # LLM 呼び出し（ツール付き）
            response = await bedrock_client.generate_with_tools(
                messages=messages,
                system_prompt=system_prompt,
                tools=agentic_tools,
                max_tokens=4096,
                temperature=0.3,
            )

            # end_turn → ループ終了
            if response.stop_reason == "end_turn":
                for block in response.content:
                    if isinstance(block, bedrock_client.TextBlock):
                        final_text += block.text
                break

            # tool_use → ツール実行
            if response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": response.content_raw})

                tool_results: list[dict[str, object]] = []
                for block in response.content:
                    if isinstance(block, bedrock_client.ToolUseBlock):
                        if block.name == "list_documents":
                            yield _sse(
                                "agentic_step",
                                {
                                    "iteration": iteration,
                                    "max_iterations": max_iterations,
                                    "status": "searching",
                                    "search_query": "ドキュメント一覧を取得",
                                },
                            )

                            try:
                                doc_list = await _list_kb_documents(
                                    knowledge_base_id, db
                                )
                            except Exception as exc:
                                logger.error("ドキュメント一覧取得でエラー: %s", exc)
                                doc_list = []

                            yield _sse(
                                "agentic_step",
                                {
                                    "iteration": iteration,
                                    "max_iterations": max_iterations,
                                    "status": "found",
                                    "result_count": len(doc_list),
                                },
                            )

                            if doc_list:
                                result_text = "ドキュメント一覧:\n" + "\n".join(
                                    f"- ID: {d['id']} | ファイル名: {d['filename']} | 種別: {d['file_type']} | 文字数: {d['char_count']}"
                                    for d in doc_list
                                )
                            else:
                                result_text = (
                                    "ナレッジベースにドキュメントがありません。"
                                )

                            tool_results.append(
                                {
                                    "type": "tool_result",
                                    "tool_use_id": block.id,
                                    "content": [{"type": "text", "text": result_text}],
                                }
                            )

                        elif block.name == "search_in_document":
                            doc_id = block.input.get("document_id", "")
                            search_query = block.input.get("query", "")
                            max_res = block.input.get("max_results", 10)

                            yield _sse(
                                "agentic_step",
                                {
                                    "iteration": iteration,
                                    "max_iterations": max_iterations,
                                    "status": "searching",
                                    "search_query": f"文書内検索: 「{search_query}」",
                                },
                            )

                            try:
                                filename, matches = await _search_in_document(
                                    doc_id,
                                    search_query,
                                    db,
                                    max_results=max_res,
                                    folder_cache=folder_cache,
                                )
                            except Exception as exc:
                                logger.error("文書内検索でエラー: %s", exc)
                                filename, matches = "", []

                            if filename and doc_id not in read_documents:
                                first_snippet = (
                                    matches[0]["content"][:300] if matches else ""
                                )
                                read_documents[doc_id] = (filename, first_snippet)

                            if matches:
                                result_parts = [
                                    f"「{search_query}」の検索結果 ({len(matches)}件):"
                                ]
                                for m in matches:
                                    result_parts.append(
                                        f"\n--- 行 {m['line_number']} (offset: {m['char_offset']}) ---\n{m['content']}"
                                    )
                                result_text = "\n".join(result_parts)
                            else:
                                result_text = f"「{search_query}」に一致する箇所は見つかりませんでした。別のキーワードで再検索してください。"

                            yield _sse(
                                "agentic_step",
                                {
                                    "iteration": iteration,
                                    "max_iterations": max_iterations,
                                    "status": "found",
                                    "result_count": len(matches),
                                },
                            )

                            tool_results.append(
                                {
                                    "type": "tool_result",
                                    "tool_use_id": block.id,
                                    "content": [{"type": "text", "text": result_text}],
                                }
                            )

                        elif block.name == "read_document_section":
                            doc_id = block.input.get("document_id", "")
                            sec_offset = block.input.get("offset", 0)
                            sec_length = block.input.get("length", 10000)

                            yield _sse(
                                "agentic_step",
                                {
                                    "iteration": iteration,
                                    "max_iterations": max_iterations,
                                    "status": "searching",
                                    "search_query": f"文書を読み込み中 (offset: {sec_offset})",
                                },
                            )

                            try:
                                (
                                    filename,
                                    content,
                                    total_chars,
                                    has_more,
                                ) = await _read_document_section(
                                    doc_id,
                                    db,
                                    offset=sec_offset,
                                    length=sec_length,
                                    folder_cache=folder_cache,
                                )
                            except Exception as exc:
                                logger.error("ドキュメント読み込みでエラー: %s", exc)
                                filename, content, total_chars, has_more = (
                                    "",
                                    "",
                                    0,
                                    False,
                                )

                            if content:
                                if doc_id not in read_documents:
                                    read_documents[doc_id] = (filename, content[:300])
                                result_text = (
                                    f"# {filename} (offset: {sec_offset}, "
                                    f"全{total_chars}文字中 {len(content)}文字表示"
                                    f"{', 続きあり' if has_more else ''})\n\n{content}"
                                )
                            else:
                                result_text = f"ドキュメント (ID: {doc_id}) が見つからないか、指定範囲に内容がありません。"

                            yield _sse(
                                "agentic_step",
                                {
                                    "iteration": iteration,
                                    "max_iterations": max_iterations,
                                    "status": "found",
                                    "result_count": 1 if content else 0,
                                },
                            )

                            tool_results.append(
                                {
                                    "type": "tool_result",
                                    "tool_use_id": block.id,
                                    "content": [{"type": "text", "text": result_text}],
                                }
                            )

                        elif block.name == "query_csv_data":
                            source_id = block.input.get("source_id", "")
                            mode = block.input.get("mode", "describe")
                            sql_query = block.input.get("sql_query", "")

                            yield _sse(
                                "agentic_step",
                                {
                                    "iteration": iteration,
                                    "max_iterations": max_iterations,
                                    "status": "searching",
                                    "search_query": (
                                        f"CSV データ分析: {mode}"
                                        if mode == "describe"
                                        else f"SQL 実行: {sql_query[:60]}"
                                    ),
                                },
                            )

                            # LLM が "datasource:xxx" 形式で渡す場合があるのでプレフィックス除去
                            clean_id = source_id.removeprefix("datasource:")
                            container_path = data_source_paths.get(clean_id, "")
                            if not container_path:
                                result_text = f"データソース (ID: {source_id}) が見つかりません。list_documents で正しい ID を確認してください。"
                            else:
                                import asyncio
                                from app.services.duckdb_query import (
                                    CsvDataSession,
                                    validate_sql,
                                )

                                # セッション内で DuckDB 接続を再利用
                                if clean_id not in csv_sessions:
                                    csv_sessions[clean_id] = CsvDataSession(
                                        container_path, source_id=clean_id
                                    )
                                session = csv_sessions[clean_id]

                                if mode == "describe":
                                    try:
                                        await asyncio.to_thread(session.prepare)
                                        tables = await asyncio.to_thread(
                                            session.describe
                                        )
                                    except Exception as exc:
                                        logger.error("CSV describe 失敗: %s", exc)
                                        tables = []

                                    if tables:
                                        total_csv_count = len(session.csv_files)
                                        parts: list[str] = []

                                        # Parquet 統合テーブルモード（テーブル名 "data"）
                                        if (
                                            len(tables) == 1
                                            and tables[0].table_name == "data"
                                        ):
                                            t = tables[0]
                                            cols_str = ", ".join(
                                                f"{c.name} ({c.dtype})"
                                                for c in t.columns
                                            )
                                            parts.append(
                                                f"統合テーブル: data（{total_csv_count} CSV ファイルを統合）\n"
                                                f"総行数: {t.row_count}\n"
                                                f"カラム: {cols_str}\n"
                                                f"※ _source_file カラムで元ファイル名を参照可能\n"
                                                f"※ SQL は `SELECT ... FROM data WHERE ...` で実行\n"
                                            )
                                            if t.sample_rows:
                                                parts.append("サンプル:")
                                                for sr in t.sample_rows:
                                                    parts.append(
                                                        "  "
                                                        + " | ".join(
                                                            f"{k}={v}"
                                                            for k, v in sr.items()
                                                        )
                                                    )
                                        else:
                                            # 従来の個別テーブルモード（フォールバック）
                                            parts.append(
                                                f"全 {total_csv_count} テーブル中、先頭 {len(tables)} 件の詳細:\n"
                                            )
                                            seen_schema: set[str] = set()
                                            for t in tables:
                                                schema_key = ",".join(
                                                    c.name for c in t.columns
                                                )
                                                if schema_key in seen_schema:
                                                    parts.append(
                                                        f"- {t.table_name}: {t.row_count}行 (同構造)\n"
                                                    )
                                                    continue
                                                seen_schema.add(schema_key)
                                                cols_str = ", ".join(
                                                    f"{c.name} ({c.dtype})"
                                                    for c in t.columns
                                                )
                                                parts.append(
                                                    f"## テーブル: {t.table_name}\n"
                                                    f"行数: {t.row_count}\n"
                                                    f"カラム: {cols_str}\n"
                                                )
                                                if t.sample_rows:
                                                    parts.append("サンプル:")
                                                    for sr in t.sample_rows:
                                                        parts.append(
                                                            "  "
                                                            + " | ".join(
                                                                f"{k}={v}"
                                                                for k, v in sr.items()
                                                            )
                                                        )
                                                parts.append("")
                                            if total_csv_count > len(tables):
                                                all_csv = session.csv_files
                                                remaining_names = ", ".join(
                                                    name
                                                    for _, name in all_csv[
                                                        len(tables) : len(tables) + 10
                                                    ]
                                                )
                                                parts.append(
                                                    f"\n残り {total_csv_count - len(tables)} テーブル: {remaining_names}..."
                                                    "\nすべて同構造。SQL の UNION ALL や個別テーブル名で参照可能。"
                                                )

                                        result_text = "\n".join(parts)
                                    else:
                                        result_text = (
                                            "CSV/TSV ファイルが見つかりませんでした。"
                                        )
                                elif mode == "query":
                                    validation_error = validate_sql(sql_query)
                                    if validation_error:
                                        result_text = f"SQL エラー: {validation_error}"
                                    else:
                                        try:
                                            qr = await asyncio.to_thread(
                                                session.execute, sql_query
                                            )
                                        except Exception as exc:
                                            logger.error("SQL 実行失敗: %s", exc)
                                            result_text = f"SQL 実行エラー: {exc}"
                                            qr = None

                                        if qr is not None:
                                            if not qr.rows:
                                                result_text = "クエリ結果: 0 行"
                                            else:
                                                header = (
                                                    "| " + " | ".join(qr.columns) + " |"
                                                )
                                                separator = (
                                                    "| "
                                                    + " | ".join(
                                                        "---" for _ in qr.columns
                                                    )
                                                    + " |"
                                                )
                                                data_rows = "\n".join(
                                                    "| " + " | ".join(row) + " |"
                                                    for row in qr.rows
                                                )
                                                result_text = f"{header}\n{separator}\n{data_rows}"
                                                if qr.truncated:
                                                    result_text += f"\n\n(結果は {qr.row_count} 行に切り詰められました)"
                                else:
                                    result_text = "mode は 'describe' または 'query' を指定してください。"

                            yield _sse(
                                "agentic_step",
                                {
                                    "iteration": iteration,
                                    "max_iterations": max_iterations,
                                    "status": "found",
                                    "result_count": 1,
                                },
                            )

                            tool_results.append(
                                {
                                    "type": "tool_result",
                                    "tool_use_id": block.id,
                                    "content": [{"type": "text", "text": result_text}],
                                }
                            )

                messages.append({"role": "user", "content": tool_results})
            else:
                for block in response.content:
                    if isinstance(block, bedrock_client.TextBlock):
                        final_text += block.text
                break
        else:
            # ループ上限到達
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "これまでに読み込んだドキュメントの内容を踏まえて、最終的な回答を生成してください。",
                        }
                    ],
                }
            )

        # 最終回答のストリーミング
        yield _sse(
            "status", {"message": "回答を生成しています...", "stage": "generating"}
        )

        if final_text:
            # ループ内で end_turn した場合: 擬似ストリーミング（20文字ずつ）
            full_answer_parts: list[str] = []
            chunk_size = 20
            for i in range(0, len(final_text), chunk_size):
                chunk = final_text[i : i + chunk_size]
                full_answer_parts.append(chunk)
                yield _sse("token", {"text": chunk})
            full_answer = "".join(full_answer_parts)
        else:
            # ループ上限到達: ストリーミング生成
            full_answer_parts = []
            try:
                async for token in bedrock_client.generate_text_stream_with_messages(
                    messages=messages,
                    system_prompt=system_prompt,
                    max_tokens=4096,
                    temperature=0.3,
                ):
                    full_answer_parts.append(token)
                    yield _sse("token", {"text": token})
            except Exception as exc:
                logger.error("最終回答生成中にエラー: %s", exc)
                error_msg = "回答の生成中にエラーが発生しました。しばらく後に再試行してください。"
                yield _sse("token", {"text": error_msg})
                full_answer_parts = [error_msg]
            full_answer = "".join(full_answer_parts)

        # ソース情報（読み込んだドキュメント一覧）
        sources_items = [
            {
                "chunk_id": "",
                "document_id": doc_id,
                "document_name": filename,
                "section_title": "",
                "score": 1.0,
                "snippet": snippet,
            }
            for doc_id, (filename, snippet) in read_documents.items()
        ]
        yield _sse("sources", {"items": sources_items})

        # DB 保存
        sources_json = json.dumps(sources_items, ensure_ascii=False)
        assistant_message_id = await _save_messages(
            query=query,
            answer=full_answer,
            search_results=[],
            session_id=session_id,
            user=user,
            db=db,
            sources_json=sources_json,
        )

        yield _sse("output", {"type": "none", "message_id": assistant_message_id})
        yield _sse(
            "complete",
            {
                "status": "ok",
                "message_id": assistant_message_id,
                "full_answer": full_answer,
            },
        )
        yield _sse("done", {})

    except Exception as exc:
        logger.exception(
            "エージェンティック検索パイプラインでエラーが発生しました: %s", exc
        )
        yield _sse(
            "error",
            {
                "message": "内部エラーが発生しました。しばらく後に再試行してください。",
                "detail": str(exc),
            },
        )
        yield _sse("done", {})
    finally:
        # CsvDataSession のクリーンアップ（DuckDB 接続・一時ファイル解放）
        for s in csv_sessions.values():
            try:
                s.close()
            except Exception:
                pass
