"""
自動タグ付けサービスモジュール。
Claude LLM とマスターデータマッチングを組み合わせてドキュメントにタグを付与する。

3段階マッチング戦略:
  1. エイリアス完全一致（MasterDataCache によるメモリ内照合）
  2. SQLite LIKE 検索（部分一致フォールバック）
  3. Qdrant セマンティック検索（ベクトル類似度フォールバック）
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure import bedrock_client
from app.infrastructure.config import config
from app.infrastructure.master_cache import MasterDataCache
from app.infrastructure.qdrant_client import search_vectors
from app.models.database import MasterLine, MasterProcess, MasterSite
from app.services.text_normalizer import normalize_query, normalize_text

logger = logging.getLogger(__name__)

# ドキュメント先頭・末尾の文字数制限
_HEAD_CHARS = 2000
_TAIL_CHARS = 500

# セマンティック検索の類似度スコア閾値とヒット数上限
_SEMANTIC_SCORE_THRESHOLD = 0.70
_SEMANTIC_LIMIT = 5

# Claude への JSON 抽出用正規表現（コードブロック除去）
_RE_JSON_BLOCK = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)

# タグタイプ一覧（Claude に明示するもの）
_TAG_TYPES = [
    "site",
    "line",
    "process",
    "category",
    "date",
    "equipment",
    "parts",
    "persons",
    "keywords",
]

# マスターマッチ対象タイプ
_MASTER_TAG_TYPES = {"site", "line", "process"}

# Qdrant master_data ペイロードのマスタータイプキー
_QDRANT_MASTER_TYPE_KEY = "master_type"
_QDRANT_MASTER_CODE_KEY = "code"
_QDRANT_MASTER_NAME_KEY = "name"


@dataclass
class TagSuggestion:
    """
    タグ提案を表すデータクラス。

    Attributes:
        tag_key: タグの種類（site / line / process / category / date / equipment / parts / persons / keywords）。
        tag_value: タグの値（表示用テキスト）。
        confidence: 信頼度スコア（0.0 〜 1.0）。
        master_type: マスターデータの種類（site / line / process、マスター非対応の場合は None）。
        master_key: マスターデータのコード（マスター非対応の場合は None）。
    """

    tag_key: str
    tag_value: str
    confidence: float
    master_type: str | None = None
    master_key: str | None = None


# ---------------------------------------------------------------------------
# 内部ユーティリティ
# ---------------------------------------------------------------------------


def _build_master_candidates_json(master_cache: MasterDataCache) -> str:
    """
    プロンプトに埋め込むマスター候補の JSON 文字列を構築する。
    サイト・ライン・工程それぞれのコード・名称・別名を含む。

    Args:
        master_cache: メモリキャッシュされたマスターデータ。

    Returns:
        JSON 文字列（ensure_ascii=False）。
    """
    candidates: dict[str, list[dict]] = {
        "sites": [],
        "lines": [],
        "processes": [],
    }

    for code, site in master_cache.sites.items():
        candidates["sites"].append(
            {
                "code": code,
                "name": site.name,
                "aliases": site.aliases,
            }
        )

    for code, line in master_cache.lines.items():
        candidates["lines"].append(
            {
                "code": code,
                "name": line.name,
                "site_code": line.site_code,
                "aliases": line.aliases,
            }
        )

    for code, process in master_cache.processes.items():
        candidates["processes"].append(
            {
                "code": code,
                "name": process.name,
                "line_code": process.line_code,
            }
        )

    return json.dumps(candidates, ensure_ascii=False)


def _build_document_excerpt(content: str) -> str:
    """
    ドキュメントから先頭 2,000 文字 + 末尾 500 文字の抜粋を生成する。

    Args:
        content: 対象ドキュメントの全テキスト。

    Returns:
        抜粋テキスト。
    """
    if len(content) <= _HEAD_CHARS + _TAIL_CHARS:
        return content

    head = content[:_HEAD_CHARS]
    tail = content[-_TAIL_CHARS:]
    return f"{head}\n\n[...中略...]\n\n{tail}"


def _build_prompt(excerpt: str, master_candidates_json: str) -> str:
    """
    Claude に渡す完全プロンプトを構築する。

    Args:
        excerpt: ドキュメント抜粋テキスト。
        master_candidates_json: マスター候補の JSON 文字列。

    Returns:
        プロンプト文字列。
    """
    return f"""以下のドキュメントを分析し、指定されたタグタイプに基づいてタグを抽出してください。

## ドキュメント内容

{excerpt}

## マスターデータ候補

```json
{master_candidates_json}
```

## タスク

上記ドキュメントから以下のタグタイプを抽出し、JSON 配列として返してください。

タグタイプ:
- site: 製造拠点・工場（マスターデータ candidates.sites と照合）
- line: 製造ライン（マスターデータ candidates.lines と照合）
- process: 製造工程（マスターデータ candidates.processes と照合）
- category: ドキュメントカテゴリ（トラブル報告・作業手順・仕様書など）
- date: 記録日・発生日・有効期限などの日付
- equipment: 設備・機械名
- parts: 部品・部材名
- persons: 担当者・作業者名
- keywords: その他の重要キーワード

## 出力形式

以下の JSON 配列のみを返してください（説明文は不要）:

```json
[
  {{
    "tag_key": "site",
    "tag_value": "拠点名または別名",
    "confidence": 0.95,
    "master_code": "マスターコードまたは null",
    "master_type": "site または null"
  }}
]
```

## ルール

1. site / line / process タグは candidates のマスターデータと照合し、一致するものがあれば master_code にそのコードを入れる
2. マスターに一致しない場合は master_code を null にする
3. confidence は 0.0〜1.0 の浮動小数点数で、確信度を表す
4. 複数のタグタイプで同じ値が該当する場合はそれぞれ出力する
5. 日付は ISO 8601 形式（YYYY-MM-DD）に正規化する
6. 確信度が 0.5 未満のタグは出力しない
7. JSON 配列のみを出力し、余分なテキストは含めない"""


def _build_system_prompt() -> str:
    """タガー用のシステムプロンプトを返す。"""
    return (
        "あなたは製造業ドキュメントの分析に特化したタグ付けシステムです。"
        "ドキュメントから構造化されたタグ情報を正確に抽出し、JSON 形式で返します。"
        "出力は必ず有効な JSON のみとし、マークダウンコードブロック以外の説明文を含めないでください。"
    )


def _parse_llm_response(raw: str) -> list[dict]:
    """
    Claude の出力テキストから JSON 配列をパースする。
    コードブロック（```json ... ```）があれば中身を取り出す。

    Args:
        raw: Claude の生レスポンス文字列。

    Returns:
        パース済みの辞書リスト。パース失敗時は空リスト。
    """
    text = raw.strip()

    # コードブロックを除去
    m = _RE_JSON_BLOCK.search(text)
    if m:
        text = m.group(1).strip()

    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
        logger.warning("tagger: LLM レスポンスが配列でない: %s", type(data))
        return []
    except json.JSONDecodeError as exc:
        logger.warning("tagger: JSON パース失敗: %s | raw=%.200s", exc, raw)
        return []


def _llm_items_to_suggestions(items: list[dict]) -> list[TagSuggestion]:
    """
    LLM が返した辞書リストを TagSuggestion リストに変換する。
    不正なアイテムはスキップする。

    Args:
        items: LLM が生成したタグ辞書のリスト。

    Returns:
        TagSuggestion のリスト。
    """
    suggestions: list[TagSuggestion] = []
    for item in items:
        tag_key = item.get("tag_key", "")
        tag_value = item.get("tag_value", "")
        if not tag_key or not tag_value:
            continue
        if tag_key not in _TAG_TYPES:
            logger.debug("tagger: 不明なタグキー '%s' をスキップ", tag_key)
            continue

        try:
            confidence = float(item.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0

        confidence = max(0.0, min(1.0, confidence))

        master_code = item.get("master_code") or None
        master_type = item.get("master_type") or None

        suggestions.append(
            TagSuggestion(
                tag_key=tag_key,
                tag_value=normalize_text(str(tag_value)),
                confidence=confidence,
                master_type=master_type if master_type in _MASTER_TAG_TYPES else None,
                master_key=master_code,
            )
        )
    return suggestions


# ---------------------------------------------------------------------------
# 3 段階マスターマッチング
# ---------------------------------------------------------------------------


def _alias_exact_match(
    query: str,
    master_cache: MasterDataCache,
) -> list[TagSuggestion]:
    """
    Stage 1: MasterDataCache のエイリアス完全一致検索。
    NFKC 正規化済み query をサイト・ライン・工程の名称・別名と照合する。

    Args:
        query: 正規化済みの検索文字列。
        master_cache: マスターデータキャッシュ。

    Returns:
        一致した TagSuggestion のリスト（信頼度 1.0）。
    """
    results: list[TagSuggestion] = []
    q_lower = query.lower()

    for code, site in master_cache.sites.items():
        names = [site.name.lower()] + [a.lower() for a in site.aliases]
        if q_lower in names:
            results.append(
                TagSuggestion(
                    tag_key="site",
                    tag_value=site.name,
                    confidence=1.0,
                    master_type="site",
                    master_key=code,
                )
            )

    for code, line in master_cache.lines.items():
        names = [line.name.lower()] + [a.lower() for a in line.aliases]
        if q_lower in names:
            results.append(
                TagSuggestion(
                    tag_key="line",
                    tag_value=line.name,
                    confidence=1.0,
                    master_type="line",
                    master_key=code,
                )
            )

    for code, process in master_cache.processes.items():
        if q_lower == process.name.lower():
            results.append(
                TagSuggestion(
                    tag_key="process",
                    tag_value=process.name,
                    confidence=1.0,
                    master_type="process",
                    master_key=code,
                )
            )

    return results


async def _sqlite_like_match(
    query: str,
    db: AsyncSession,
) -> list[TagSuggestion]:
    """
    Stage 2: SQLite LIKE 検索による部分一致マッチング。
    MasterSite / MasterLine / MasterProcess の name・aliases カラムを対象とする。

    Args:
        query: 正規化済みの検索文字列。
        db: SQLAlchemy 非同期セッション。

    Returns:
        一致した TagSuggestion のリスト（信頼度 0.85）。
    """
    results: list[TagSuggestion] = []
    like_pattern = f"%{query}%"

    # MasterSite
    site_stmt = (
        select(MasterSite)
        .where(
            or_(
                MasterSite.name.like(like_pattern),
                MasterSite.aliases.like(like_pattern),
            )
        )
        .limit(5)
    )
    site_rows = (await db.execute(site_stmt)).scalars().all()
    for row in site_rows:
        results.append(
            TagSuggestion(
                tag_key="site",
                tag_value=row.name,
                confidence=0.85,
                master_type="site",
                master_key=row.code,
            )
        )

    # MasterLine
    line_stmt = (
        select(MasterLine)
        .where(
            or_(
                MasterLine.name.like(like_pattern),
                MasterLine.aliases.like(like_pattern),
            )
        )
        .limit(5)
    )
    line_rows = (await db.execute(line_stmt)).scalars().all()
    for row in line_rows:
        results.append(
            TagSuggestion(
                tag_key="line",
                tag_value=row.name,
                confidence=0.85,
                master_type="line",
                master_key=row.code,
            )
        )

    # MasterProcess
    process_stmt = (
        select(MasterProcess).where(MasterProcess.name.like(like_pattern)).limit(5)
    )
    process_rows = (await db.execute(process_stmt)).scalars().all()
    for row in process_rows:
        results.append(
            TagSuggestion(
                tag_key="process",
                tag_value=row.name,
                confidence=0.85,
                master_type="process",
                master_key=row.code,
            )
        )

    return results


async def _qdrant_semantic_match(query: str) -> list[TagSuggestion]:
    """
    Stage 3: Qdrant セマンティック検索による類似マスターマッチング。
    クエリをベクトル化し master_data コレクションで類似エントリを検索する。

    Args:
        query: 検索クエリ文字列。

    Returns:
        類似度スコアが閾値以上の TagSuggestion のリスト。
    """
    try:
        query_vector = await bedrock_client.embed_query(query)
    except Exception as exc:
        logger.warning("tagger: embed_query 失敗: %s", exc)
        return []

    try:
        # Qdrant クライアントは同期 gRPC のため別スレッドで実行しイベントループをブロックしない
        search_results = await asyncio.to_thread(
            search_vectors,
            collection=config.QDRANT_MASTER_COLLECTION,
            query_vector=query_vector,
            limit=_SEMANTIC_LIMIT,
            score_threshold=_SEMANTIC_SCORE_THRESHOLD,
        )
    except Exception as exc:
        logger.warning("tagger: Qdrant semantic search 失敗: %s", exc)
        return []

    results: list[TagSuggestion] = []
    for hit in search_results:
        master_type = hit.payload.get(_QDRANT_MASTER_TYPE_KEY)
        master_code = hit.payload.get(_QDRANT_MASTER_CODE_KEY)
        master_name = hit.payload.get(_QDRANT_MASTER_NAME_KEY, "")

        if not master_type or not master_code or master_type not in _MASTER_TAG_TYPES:
            continue

        results.append(
            TagSuggestion(
                tag_key=master_type,
                tag_value=master_name,
                confidence=round(
                    hit.score * 0.9, 4
                ),  # セマンティック信頼度は 0.9 倍で控えめに
                master_type=master_type,
                master_key=master_code,
            )
        )

    return results


async def suggest_tags_from_master(
    query: str,
    master_cache: MasterDataCache,
    db: AsyncSession,
) -> list[TagSuggestion]:
    """
    3 段階マスターマッチングを実行し、マスターに紐付くタグ候補を返す。

    Stage 1 でヒットした場合は Stage 2・3 を実行しない（早期終了）。
    Stage 1 でヒットしない場合は Stage 2 を試み、それでもヒットしなければ Stage 3 を実行する。

    Args:
        query: マッチング対象の検索テキスト（正規化前でも可）。
        master_cache: マスターデータキャッシュ。
        db: SQLAlchemy 非同期セッション。

    Returns:
        TagSuggestion のリスト。重複は master_key で排除される。
    """
    normalized = normalize_query(query)
    if not normalized:
        return []

    # Stage 1: エイリアス完全一致
    stage1 = _alias_exact_match(normalized, master_cache)
    if stage1:
        logger.debug(
            "tagger: Stage1 完全一致: query=%s hits=%d", normalized, len(stage1)
        )
        return stage1

    # Stage 2: SQLite LIKE 検索
    stage2 = await _sqlite_like_match(normalized, db)
    if stage2:
        logger.debug(
            "tagger: Stage2 LIKE 一致: query=%s hits=%d", normalized, len(stage2)
        )
        return stage2

    # Stage 3: セマンティック検索
    stage3 = await _qdrant_semantic_match(normalized)
    logger.debug(
        "tagger: Stage3 セマンティック: query=%s hits=%d", normalized, len(stage3)
    )
    return stage3


# ---------------------------------------------------------------------------
# メイン公開 API
# ---------------------------------------------------------------------------


def _deduplicate_suggestions(suggestions: list[TagSuggestion]) -> list[TagSuggestion]:
    """
    同一 (tag_key, master_key) の重複を除去し、信頼度の高いものを残す。
    master_key が None のタグは (tag_key, tag_value) で重複排除する。

    Args:
        suggestions: 重複を含む可能性がある TagSuggestion のリスト。

    Returns:
        重複を排除した TagSuggestion のリスト（信頼度降順）。
    """
    seen_master: dict[tuple[str, str], TagSuggestion] = {}
    seen_value: dict[tuple[str, str], TagSuggestion] = {}

    for s in sorted(suggestions, key=lambda x: x.confidence, reverse=True):
        if s.master_key is not None:
            key = (s.tag_key, s.master_key)
            if key not in seen_master:
                seen_master[key] = s
        else:
            key = (s.tag_key, s.tag_value)
            if key not in seen_value:
                seen_value[key] = s

    merged = list(seen_master.values()) + list(seen_value.values())
    merged.sort(key=lambda x: x.confidence, reverse=True)
    return merged


async def auto_tag_document(
    content: str,
    db: AsyncSession,
    master_cache: MasterDataCache,
) -> list[TagSuggestion]:
    """
    ドキュメントを Claude LLM で解析し、マスターマッチングを加えてタグ候補を返す。

    処理フロー:
      1. ドキュメントの先頭 2,000 文字 + 末尾 500 文字を抽出
      2. マスター候補 JSON を構築してプロンプトに埋め込む
      3. Claude に temperature=0 で問い合わせ（決定論的）
      4. LLM レスポンスをパースして TagSuggestion に変換
      5. site / line / process タグに対して 3 段階マスターマッチングを補完実行
      6. 重複排除して信頼度降順で返す

    Args:
        content: タグ付け対象のドキュメント全テキスト。
        db: SQLAlchemy 非同期セッション（SQLite LIKE 検索に使用）。
        master_cache: メモリキャッシュされたマスターデータ。

    Returns:
        TagSuggestion のリスト（信頼度降順、重複排除済み）。
        LLM 呼び出しに失敗した場合は空リストを返す。
    """
    if not content or not content.strip():
        logger.warning("tagger: ドキュメントが空のためスキップします")
        return []

    excerpt = _build_document_excerpt(content)
    master_candidates_json = _build_master_candidates_json(master_cache)
    prompt = _build_prompt(excerpt, master_candidates_json)
    system_prompt = _build_system_prompt()

    # LLM 呼び出し（temperature=0 で決定論的）
    try:
        raw_response = await bedrock_client.generate_text(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=2048,
            temperature=0.0,
        )
    except Exception as exc:
        logger.error("tagger: LLM 呼び出し失敗: %s", exc, exc_info=True)
        return []

    items = _parse_llm_response(raw_response)
    llm_suggestions = _llm_items_to_suggestions(items)
    logger.info("tagger: LLM から %d 件のタグ候補を取得", len(llm_suggestions))

    # マスタータグ（site/line/process）に対して 3 段階マッチングを補完する
    # LLM がマスターコードを返していない場合、タグ値でマッチングを試みる
    supplemented: list[TagSuggestion] = []
    for suggestion in llm_suggestions:
        if suggestion.tag_key in _MASTER_TAG_TYPES and suggestion.master_key is None:
            matched = await suggest_tags_from_master(
                query=suggestion.tag_value,
                master_cache=master_cache,
                db=db,
            )
            # マッチが得られた場合は同タグキーのものだけを採用し、元のタグを置換
            same_type = [m for m in matched if m.tag_key == suggestion.tag_key]
            if same_type:
                # 元の LLM の信頼度と比較して高い方を採用
                for m in same_type:
                    m.confidence = min(
                        1.0, (m.confidence + suggestion.confidence) / 2 + 0.05
                    )
                supplemented.extend(same_type)
                continue
        supplemented.append(suggestion)

    # 重複排除して信頼度降順に並べて返す
    result = _deduplicate_suggestions(supplemented)
    logger.info("tagger: 最終タグ候補 %d 件（重複排除後）", len(result))
    return result
