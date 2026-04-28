"""
チャット・セッション管理ルーターモジュール。
RAG チャット、セッション履歴、メッセージ評価の API エンドポイントを提供する。

X-User-Id ヘッダーによるユーザー識別を使用する。
FTS5 仮想テーブル（messages_fts）によるセッション横断全文検索をサポートする。
"""

from __future__ import annotations

import csv
import io
import json
import logging
import unicodedata
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.infrastructure.db import get_db
from app.models.database import ChatOutput, Document, Message, Session
from app.services.memory_extractor import extract_and_save_memories
from app.services.rag import run_agentic_search_pipeline, run_rag_pipeline
from app.services.user_profile import update_user_profile

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


# ---------------------------------------------------------------------------
# Pydantic スキーマ
# ---------------------------------------------------------------------------


class SessionSummary(BaseModel):
    """セッション一覧の各エントリ。"""

    id: str
    title: Optional[str]
    knowledge_base_id: str
    created_at: str
    updated_at: str
    message_count: int
    last_message_preview: Optional[str]

    model_config = {"from_attributes": True}


class SessionListResponse(BaseModel):
    """GET /sessions レスポンス。"""

    sessions: list[SessionSummary]
    total: int


class MessageResponse(BaseModel):
    """セッション詳細に含まれる各メッセージ。"""

    id: str
    role: str
    content: str
    sources: Optional[Any]
    rating: Optional[int]
    input_type: str
    response_mode: Optional[str]
    is_cancelled: bool
    created_at: str
    has_output: bool

    model_config = {"from_attributes": True}


class SessionDetailResponse(BaseModel):
    """GET /sessions/{session_id} レスポンス。"""

    id: str
    title: Optional[str]
    knowledge_base_id: str
    created_at: str
    updated_at: str
    messages: list[MessageResponse]

    model_config = {"from_attributes": True}


class RatingRequest(BaseModel):
    """PUT /messages/{message_id}/rating リクエストボディ。"""

    rating: int = Field(..., ge=1, le=5, description="評価値（1〜5）")


class RatingResponse(BaseModel):
    """PUT /messages/{message_id}/rating レスポンス。"""

    message_id: str
    rating: int


class ChatRequest(BaseModel):
    """POST /chat リクエストボディ。"""

    content: str = Field(..., min_length=1, description="ユーザーのメッセージ内容")
    session_id: Optional[str] = Field(
        default=None, description="会話セッション ID（None の場合は新規作成）"
    )
    knowledge_base_id: str = Field(..., description="検索対象ナレッジベース ID")
    input_type: str = Field(default="text", description="入力タイプ（text | voice）")
    search_mode: str = Field(default="normal", description="検索モード（normal | agentic）")


class SearchMatch(BaseModel):
    """検索結果の各マッチ行。"""

    message_id: str
    snippet: str
    role: str
    created_at: str


class SearchResultGroup(BaseModel):
    """検索結果のセッション単位グループ。"""

    session_id: str
    session_title: Optional[str]
    matches: list[SearchMatch]


class SearchResponse(BaseModel):
    """GET /sessions/search レスポンス。"""

    query: str
    results: list[SearchResultGroup]


# ---------------------------------------------------------------------------
# 依存性注入
# ---------------------------------------------------------------------------


def get_user_id(x_user_id: str = Header(..., alias="X-User-Id")) -> str:
    """
    X-User-Id ヘッダーからユーザー ID を取得する FastAPI 依存性関数。

    Args:
        x_user_id: リクエストヘッダーの X-User-Id 値。

    Returns:
        ユーザー ID 文字列。

    Raises:
        HTTPException: X-User-Id ヘッダーが空の場合。
    """
    user_id = x_user_id.strip()
    if not user_id:
        raise HTTPException(
            status_code=400, detail="X-User-Id header must not be empty"
        )
    return user_id


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------


def _parse_sources(raw: Optional[str]) -> Any:
    """
    sources フィールドの JSON 文字列をパースして返す。
    パースに失敗した場合は元の文字列を返す。

    Args:
        raw: JSON 文字列または None。

    Returns:
        パース済みオブジェクト、None、または元の文字列。
    """
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw


def _message_preview(content: str, max_length: int = 100) -> str:
    """
    メッセージ内容の先頭 max_length 文字をプレビューとして返す。

    Args:
        content: メッセージ本文。
        max_length: 切り詰める最大文字数。

    Returns:
        プレビュー文字列。
    """
    content = content.strip()
    if len(content) <= max_length:
        return content
    return content[:max_length] + "..."


def _normalize_query(q: str) -> str:
    """
    検索クエリに NFKC 正規化を適用して返す。

    Args:
        q: 正規化前の検索クエリ文字列。

    Returns:
        NFKC 正規化済みクエリ文字列。
    """
    return unicodedata.normalize("NFKC", q)


async def _get_session_or_404(session_id: str, db: AsyncSession) -> Session:
    """
    セッションを取得する。存在しない場合は 404 を送出する。

    Args:
        session_id: 対象セッションの ID。
        db: 非同期データベースセッション。

    Returns:
        Session ORM インスタンス。

    Raises:
        HTTPException: セッションが見つからない場合。
    """
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return session


def _build_message_response(msg: Message) -> MessageResponse:
    """
    Message ORM インスタンスを MessageResponse Pydantic モデルに変換する。

    Args:
        msg: Message ORM インスタンス。

    Returns:
        MessageResponse インスタンス。
    """
    return MessageResponse(
        id=msg.id,
        role=msg.role,
        content=msg.content,
        sources=_parse_sources(msg.sources),
        rating=msg.rating,
        input_type=msg.input_type,
        response_mode=msg.response_mode,
        is_cancelled=bool(msg.is_cancelled),
        created_at=msg.created_at,
        has_output=msg.chat_output is not None,
    )


# ---------------------------------------------------------------------------
# エンドポイント
# ---------------------------------------------------------------------------


@router.post("/chat")
async def create_chat(
    body: ChatRequest,
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """
    RAG チャットエンドポイント（SSE ストリーミングレスポンス）。

    session_id が None の場合は新しいセッションを作成する。
    run_rag_pipeline() が yield する SSE イベントをそのままストリーミングする。

    Args:
        body: ChatRequest リクエストボディ。
        user_id: X-User-Id ヘッダーから取得したユーザー ID。
        db: 非同期データベースセッション。

    Returns:
        StreamingResponse（text/event-stream）。
    """
    now = datetime.now(timezone.utc).isoformat()

    # セッションの取得または新規作成
    session_id = body.session_id
    if session_id is None:
        session_id = str(uuid.uuid4())
        new_session = Session(
            id=session_id,
            user_id=user_id,
            knowledge_base_id=body.knowledge_base_id,
            title=body.content[:50] if len(body.content) > 50 else body.content,
            created_at=now,
            updated_at=now,
        )
        db.add(new_session)
        await db.commit()
        logger.info(
            "新規セッションを作成しました: session_id=%s, user_id=%s",
            session_id,
            user_id,
        )
    else:
        # 既存セッションの存在確認と所有者確認
        result = await db.execute(select(Session).where(Session.id == session_id))
        existing_session = result.scalar_one_or_none()
        if existing_session is None:
            raise HTTPException(
                status_code=404,
                detail=f"Session {session_id} not found",
            )
        if existing_session.user_id != user_id:
            raise HTTPException(
                status_code=403,
                detail="You do not have access to this session",
            )

    async def event_generator():
        full_answer = ""

        if body.search_mode == "agentic":
            pipeline = run_agentic_search_pipeline(
                query=body.content,
                session_id=session_id,
                knowledge_base_id=body.knowledge_base_id,
                user_id=user_id,
                db=db,
            )
        else:
            pipeline = run_rag_pipeline(
                query=body.content,
                session_id=session_id,
                knowledge_base_id=body.knowledge_base_id,
                user_id=user_id,
                db=db,
            )

        async for event in pipeline:
            # complete イベントから full_answer を取得する
            if '"event": "complete"' in event:
                try:
                    payload = json.loads(event.removeprefix("data: ").strip())
                    full_answer = payload.get("data", {}).get("full_answer", "")
                except (json.JSONDecodeError, AttributeError):
                    pass
            yield event

        # 自動メモリ抽出（エラーがあってもチャットに影響しない）
        if full_answer:
            try:
                await extract_and_save_memories(
                    user_id=user_id,
                    user_query=body.content,
                    assistant_answer=full_answer,
                    db=db,
                )
            except Exception as exc:
                logger.warning("メモリ自動抽出に失敗: %s", exc)

        # RAG パイプライン完了後にユーザープロファイルを非同期で更新する
        # エラーが発生しても update_user_profile 内でキャッチされるためチャットには影響しない
        await update_user_profile(user_id=user_id, db=db)

    return StreamingResponse(
        content=event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/sessions/search", response_model=SearchResponse)
async def search_sessions(
    q: str = Query(..., min_length=1, description="全文検索クエリ"),
    knowledge_base_id: Optional[str] = Query(
        default=None, description="ナレッジベース ID でフィルタ"
    ),
    limit: int = Query(default=20, ge=1, le=100, description="最大取得件数"),
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
) -> SearchResponse:
    """
    FTS5 全文検索でセッション横断検索を行う。

    messages_fts 仮想テーブルを使って content を検索し、
    セッション単位にグループ化して返す。NFKC 正規化を適用する。

    Args:
        q: 検索クエリ（NFKC 正規化が適用される）。
        knowledge_base_id: フィルタ対象ナレッジベース ID（省略可）。
        limit: セッショングループの最大返却数。
        user_id: X-User-Id ヘッダーから取得したユーザー ID。
    """
    normalized_q = _normalize_query(q)

    # FTS5 は仮想テーブルのため ORM を使わず生 SQL で実行する。
    # content='messages' コンテンツテーブル設定のため rowid は messages.rowid に対応する。
    # snippet 関数: カラムインデックス 0 (content)、ハイライトタグ、省略記号、トークン数。
    fts_sql = text(
        """
        SELECT
            m.id          AS message_id,
            snippet(messages_fts, 0, '<mark>', '</mark>', '...', 32) AS snippet,
            m.role        AS role,
            m.created_at  AS created_at,
            s.id          AS session_id,
            s.title       AS session_title,
            s.knowledge_base_id AS knowledge_base_id,
            s.user_id     AS session_user_id
        FROM messages_fts
        JOIN messages m ON messages_fts.rowid = m.rowid
        JOIN sessions s ON m.session_id = s.id
        WHERE messages_fts MATCH :query
          AND s.user_id = :user_id
        ORDER BY rank
        LIMIT :limit
        """
    )

    params: dict[str, Any] = {
        "query": normalized_q,
        "user_id": user_id,
        "limit": limit
        * 10,  # グループ化後に limit 件のセッションを確保するため多めに取得
    }

    result = await db.execute(fts_sql, params)
    rows = result.fetchall()

    # knowledge_base_id フィルタをアプリ側で適用（SQLite FTS5 JOIN 制約のため）
    if knowledge_base_id is not None:
        rows = [r for r in rows if r.knowledge_base_id == knowledge_base_id]

    # セッション単位にグループ化（挿入順序を維持するため dict を使用）
    grouped: dict[str, SearchResultGroup] = {}
    for row in rows:
        sid = row.session_id
        if sid not in grouped:
            if len(grouped) >= limit:
                break
            grouped[sid] = SearchResultGroup(
                session_id=sid,
                session_title=row.session_title,
                matches=[],
            )
        grouped[sid].matches.append(
            SearchMatch(
                message_id=row.message_id,
                snippet=row.snippet,
                role=row.role,
                created_at=row.created_at,
            )
        )

    return SearchResponse(query=q, results=list(grouped.values()))


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(
    limit: int = Query(default=20, ge=1, le=100, description="最大取得件数"),
    offset: int = Query(default=0, ge=0, description="取得開始オフセット"),
    knowledge_base_id: Optional[str] = Query(
        default=None, description="ナレッジベース ID でフィルタ"
    ),
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
) -> SessionListResponse:
    """
    ユーザーのセッション一覧を updated_at の降順で取得する。

    各エントリにメッセージ数と最終メッセージプレビューを付与する。
    knowledge_base_id を指定した場合はそのナレッジベースのセッションのみ返す。

    Args:
        limit: 最大取得件数（1〜100）。
        offset: 取得開始位置。
        knowledge_base_id: フィルタ対象ナレッジベース ID（省略可）。
        user_id: X-User-Id ヘッダーから取得したユーザー ID。
    """
    base_filter = [Session.user_id == user_id]
    if knowledge_base_id is not None:
        base_filter.append(Session.knowledge_base_id == knowledge_base_id)

    # 総件数を取得
    total_result = await db.execute(select(func.count(Session.id)).where(*base_filter))
    total = total_result.scalar_one() or 0

    # セッション一覧を取得（messages を eager load）
    sessions_result = await db.execute(
        select(Session)
        .where(*base_filter)
        .options(selectinload(Session.messages))
        .order_by(Session.updated_at.desc())
        .limit(limit)
        .offset(offset)
    )
    sessions = sessions_result.scalars().all()

    summaries: list[SessionSummary] = []
    for session in sessions:
        msgs = sorted(session.messages, key=lambda m: m.created_at)
        last_msg = msgs[-1] if msgs else None
        summaries.append(
            SessionSummary(
                id=session.id,
                title=session.title,
                knowledge_base_id=session.knowledge_base_id,
                created_at=session.created_at,
                updated_at=session.updated_at,
                message_count=len(msgs),
                last_message_preview=(
                    _message_preview(last_msg.content) if last_msg else None
                ),
            )
        )

    return SessionListResponse(sessions=summaries, total=total)


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session(
    session_id: str = Path(..., description="セッション ID"),
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
) -> SessionDetailResponse:
    """
    指定セッションの詳細を全メッセージとともに取得する。

    メッセージは created_at 昇順で返す。各メッセージに has_output フラグを付与する。

    Args:
        session_id: 対象セッションの ID。
        user_id: X-User-Id ヘッダーから取得したユーザー ID（閲覧権限確認用）。
    """
    result = await db.execute(
        select(Session)
        .where(Session.id == session_id)
        .options(selectinload(Session.messages).selectinload(Message.chat_output))
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    # 所有者確認（閲覧も所有者のみ許可）
    if session.user_id != user_id:
        raise HTTPException(
            status_code=403, detail="You do not have access to this session"
        )

    sorted_messages = sorted(session.messages, key=lambda m: m.created_at)

    response = SessionDetailResponse(
        id=session.id,
        title=session.title,
        knowledge_base_id=session.knowledge_base_id,
        created_at=session.created_at,
        updated_at=session.updated_at,
        messages=[_build_message_response(msg) for msg in sorted_messages],
    )

    # document_name が空のソースを DB の filename で補完する
    missing_doc_ids: set[str] = set()
    for msg_resp in response.messages:
        if not isinstance(msg_resp.sources, list):
            continue
        for src in msg_resp.sources:
            if (
                isinstance(src, dict)
                and src.get("document_id")
                and not src.get("document_name")
            ):
                missing_doc_ids.add(src["document_id"])

    if missing_doc_ids:
        doc_result = await db.execute(
            select(Document.id, Document.filename).where(
                Document.id.in_(missing_doc_ids)
            )
        )
        doc_name_map = {row.id: row.filename for row in doc_result}
        for msg_resp in response.messages:
            if not isinstance(msg_resp.sources, list):
                continue
            for src in msg_resp.sources:
                if (
                    isinstance(src, dict)
                    and src.get("document_id")
                    and not src.get("document_name")
                ):
                    src["document_name"] = doc_name_map.get(src["document_id"], "")

    return response


@router.delete("/sessions/{session_id}", status_code=204, response_class=Response)
async def delete_session(
    session_id: str = Path(..., description="セッション ID"),
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    指定セッションを削除する。セッションの所有者のみ削除できる。

    ORM カスケードにより関連する messages / chat_outputs も連鎖削除される。

    Args:
        session_id: 削除対象セッションの ID。
        user_id: X-User-Id ヘッダーから取得したユーザー ID。

    Raises:
        HTTPException 404: セッションが見つからない場合。
        HTTPException 403: 所有者でない場合。
    """
    session = await _get_session_or_404(session_id, db)

    if session.user_id != user_id:
        raise HTTPException(
            status_code=403,
            detail="You are not the owner of this session",
        )

    await db.delete(session)
    logger.info("Deleted session id=%s by user_id=%s", session_id, user_id)
    return Response(status_code=204)


@router.get("/chat/output/{message_id}")
async def get_message_output(
    message_id: str = Path(..., description="メッセージ ID"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    指定メッセージの構造化出力データを取得する。

    chat_outputs テーブルから output_type、table_data、chart_config を返す。
    table_data と chart_config は JSON 文字列からパースしたオブジェクトとして返す。

    Args:
        message_id: 対象メッセージの ID。

    Returns:
        {
            "message_id": str,
            "output_type": str,
            "table_data": dict | None,
            "chart_config": dict | None,
            "sql_executed": str | None,
            "row_count": int,
            "created_at": str,
        }

    Raises:
        HTTPException 404: 指定メッセージの出力データが存在しない場合。
    """
    result = await db.execute(
        select(ChatOutput).where(ChatOutput.message_id == message_id)
    )
    chat_output = result.scalar_one_or_none()

    if chat_output is None:
        raise HTTPException(
            status_code=404,
            detail=f"Output for message {message_id} not found",
        )

    table_data: Any = None
    if chat_output.table_data is not None:
        try:
            table_data = json.loads(chat_output.table_data)
        except (json.JSONDecodeError, TypeError):
            table_data = None

    chart_config: Any = None
    if chat_output.chart_config is not None:
        try:
            chart_config = json.loads(chat_output.chart_config)
        except (json.JSONDecodeError, TypeError):
            chart_config = None

    return {
        "message_id": chat_output.message_id,
        "output_type": chat_output.output_type,
        "table_data": table_data,
        "chart_config": chart_config,
        "sql_executed": chat_output.sql_executed,
        "row_count": chat_output.row_count,
        "created_at": chat_output.created_at,
    }


@router.get("/chat/output/{message_id}/csv")
async def get_message_output_csv(
    message_id: str = Path(..., description="メッセージ ID"),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """
    指定メッセージの出力データを CSV 形式でダウンロードする。

    BOM 付き UTF-8 エンコーディング（Excel 互換）で出力する。
    Content-Disposition ヘッダーに output_{message_id}.csv のファイル名を設定する。

    Args:
        message_id: 対象メッセージの ID。

    Returns:
        StreamingResponse（text/csv）。BOM 付き UTF-8 エンコード。

    Raises:
        HTTPException 404: 出力データが存在しない場合。
        HTTPException 400: テーブルデータが存在しない場合。
    """
    result = await db.execute(
        select(ChatOutput).where(ChatOutput.message_id == message_id)
    )
    chat_output = result.scalar_one_or_none()

    if chat_output is None:
        raise HTTPException(
            status_code=404,
            detail=f"Output for message {message_id} not found",
        )

    if chat_output.table_data is None:
        raise HTTPException(
            status_code=400,
            detail=f"Message {message_id} has no table data to export",
        )

    try:
        table_data = json.loads(chat_output.table_data)
    except (json.JSONDecodeError, TypeError) as exc:
        raise HTTPException(
            status_code=500,
            detail="テーブルデータの解析に失敗しました",
        ) from exc

    columns: list[dict] = table_data.get("columns", [])
    rows: list[dict] = table_data.get("rows", [])

    # BOM 付き UTF-8 で CSV をメモリ上に生成する（Excel 互換）
    output = io.StringIO()
    writer = csv.writer(output)

    # ヘッダー行（label を使用する）
    header = [col.get("label", col.get("key", "")) for col in columns]
    writer.writerow(header)

    # データ行（カラム key 順に値を取得する）
    col_keys = [col.get("key", "") for col in columns]
    for row in rows:
        writer.writerow([row.get(key, "") for key in col_keys])

    # BOM (U+FEFF) を先頭に付加して Excel での文字化けを防ぐ
    csv_content = "\ufeff" + output.getvalue()
    csv_bytes = csv_content.encode("utf-8")

    filename = f"output_{message_id}.csv"
    logger.info(
        "CSV ダウンロード: message_id=%s, rows=%d, filename=%s",
        message_id,
        len(rows),
        filename,
    )

    return StreamingResponse(
        content=iter([csv_bytes]),
        media_type="text/csv; charset=utf-8-sig",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.put(
    "/messages/{message_id}/rating", status_code=200, response_model=RatingResponse
)
async def rate_message(
    message_id: str = Path(..., description="メッセージ ID"),
    body: RatingRequest = ...,
    db: AsyncSession = Depends(get_db),
) -> RatingResponse:
    """
    アシスタントメッセージに評価（1〜5）を付与する。

    アシスタントメッセージのみ評価可能。ユーザーメッセージへの評価は 400 を返す。

    Args:
        message_id: 評価対象メッセージの ID。
        body: { rating: int } 評価値（1〜5）を含むリクエストボディ。

    Raises:
        HTTPException 404: メッセージが見つからない場合。
        HTTPException 400: アシスタントメッセージでない場合。
    """
    result = await db.execute(select(Message).where(Message.id == message_id))
    message = result.scalar_one_or_none()
    if message is None:
        raise HTTPException(status_code=404, detail=f"Message {message_id} not found")

    if message.role != "assistant":
        raise HTTPException(
            status_code=400,
            detail="Only assistant messages can be rated",
        )

    message.rating = body.rating
    await db.flush()
    logger.info("Rated message id=%s rating=%d", message_id, body.rating)

    return RatingResponse(message_id=message_id, rating=body.rating)
