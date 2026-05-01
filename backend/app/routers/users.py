"""
ユーザー管理ルーターモジュール。
ユーザー設定、行動プロファイル、メモリの API エンドポイントを提供する。

X-User-Id ヘッダーによるユーザー識別を使用し、未存在ユーザーは自動生成する。
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db import get_db
import uuid

from app.models.database import (
    Message,
    Session,
    User,
    UserBehavior,
    UserMemory,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])

# ---------------------------------------------------------------------------
# Pydantic スキーマ
# ---------------------------------------------------------------------------


class UserResponse(BaseModel):
    id: str
    nickname: Optional[str]
    rerank_enabled: bool
    hybrid_search_enabled: bool
    retrieval_count: int
    response_mode: str
    search_mode: str
    agentic_max_iterations: int
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class UpdateSettingsRequest(BaseModel):
    nickname: Optional[str] = Field(default=None, max_length=100)
    rerank_enabled: Optional[bool] = None
    hybrid_search_enabled: Optional[bool] = None
    retrieval_count: Optional[int] = Field(default=None, ge=1, le=50)
    response_mode: Optional[Literal["simple", "detailed"]] = None
    search_mode: Optional[Literal["normal", "agentic"]] = None
    agentic_max_iterations: Optional[int] = Field(default=None, ge=1, le=15)


class UserBehaviorResponse(BaseModel):
    user_id: str
    frequent_lines: list[str]
    frequent_categories: list[str]
    recent_context: Optional[str]
    total_sessions: int
    total_messages: int


class UserMemoryResponse(BaseModel):
    id: str
    content: str
    source: str
    created_at: str
    updated_at: str


class CreateMemoryRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)


class UpdateMemoryRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)


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
        HTTPException: X-User-Id ヘッダーが空または不正な場合。
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


def _now_iso() -> str:
    """現在時刻を UTC ISO 8601 文字列で返す。"""
    return datetime.now(UTC).isoformat()


def _user_to_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        nickname=user.nickname,
        rerank_enabled=bool(user.rerank_enabled),
        hybrid_search_enabled=bool(user.hybrid_search_enabled),
        retrieval_count=user.retrieval_count,
        response_mode=user.response_mode,
        search_mode=user.search_mode,
        agentic_max_iterations=user.agentic_max_iterations,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


async def _get_or_create_user(user_id: str, db: AsyncSession) -> User:
    """
    ユーザーを取得する。存在しない場合は新規作成して返す。

    Args:
        user_id: ユーザー識別子（フロントエンドの localStorage UUID）。
        db: 非同期データベースセッション。

    Returns:
        User ORM インスタンス。
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        now = _now_iso()
        # デフォルト値は ORM (models/database.py User クラス) と統一する。
        user = User(
            id=user_id,
            nickname=None,
            rerank_enabled=0,
            hybrid_search_enabled=1,
            retrieval_count=20,
            response_mode="detailed",
            search_mode="agentic",
            agentic_max_iterations=5,
            created_at=now,
            updated_at=now,
        )
        db.add(user)
        await db.flush()
        logger.info("Created new user: %s", user_id)

    return user


# ---------------------------------------------------------------------------
# エンドポイント
# ---------------------------------------------------------------------------


@router.get("/me", response_model=UserResponse)
async def get_current_user(
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """
    X-User-Id ヘッダーに対応するユーザー情報を取得する。
    ユーザーが存在しない場合はデフォルト設定で新規作成する。
    """
    user = await _get_or_create_user(user_id, db)
    return _user_to_response(user)


@router.put("/me/settings", status_code=200, response_model=UserResponse)
async def update_user_settings(
    body: UpdateSettingsRequest,
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """
    現在のユーザーの設定（ニックネーム、検索設定、応答モード）を更新する。

    Args:
        body: 更新するフィールドを含むリクエストボディ。未指定フィールドは変更しない。
    """
    user = await _get_or_create_user(user_id, db)

    if body.nickname is not None:
        user.nickname = body.nickname
    if body.rerank_enabled is not None:
        user.rerank_enabled = int(body.rerank_enabled)
    if body.hybrid_search_enabled is not None:
        user.hybrid_search_enabled = int(body.hybrid_search_enabled)
    if body.retrieval_count is not None:
        user.retrieval_count = body.retrieval_count
    if body.response_mode is not None:
        user.response_mode = body.response_mode
    if body.search_mode is not None:
        user.search_mode = body.search_mode
    if body.agentic_max_iterations is not None:
        user.agentic_max_iterations = body.agentic_max_iterations

    user.updated_at = _now_iso()
    await db.flush()
    return _user_to_response(user)


@router.get("/me/behavior", response_model=UserBehaviorResponse)
async def get_user_behavior(
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
) -> UserBehaviorResponse:
    """
    現在のユーザーの行動プロファイル（検索傾向、セッション数など）を取得する。
    行動データが未記録の場合は空のプロファイルを返す。
    """
    await _get_or_create_user(user_id, db)

    # UserBehavior レコードを取得
    behavior_result = await db.execute(
        select(UserBehavior).where(UserBehavior.user_id == user_id)
    )
    behavior = behavior_result.scalar_one_or_none()

    frequent_lines: list[str] = []
    frequent_categories: list[str] = []
    recent_context: Optional[str] = None

    if behavior is not None:
        if behavior.frequent_lines:
            try:
                frequent_lines = json.loads(behavior.frequent_lines)
            except (json.JSONDecodeError, TypeError):
                frequent_lines = []
        if behavior.frequent_categories:
            try:
                frequent_categories = json.loads(behavior.frequent_categories)
            except (json.JSONDecodeError, TypeError):
                frequent_categories = []
        recent_context = behavior.recent_context

    # セッション・メッセージ数を集計
    session_count_result = await db.execute(
        select(func.count(Session.id)).where(Session.user_id == user_id)
    )
    total_sessions: int = session_count_result.scalar_one() or 0

    message_count_result = await db.execute(
        select(func.count(Message.id))
        .join(Session, Message.session_id == Session.id)
        .where(Session.user_id == user_id)
    )
    total_messages: int = message_count_result.scalar_one() or 0

    return UserBehaviorResponse(
        user_id=user_id,
        frequent_lines=frequent_lines,
        frequent_categories=frequent_categories,
        recent_context=recent_context,
        total_sessions=total_sessions,
        total_messages=total_messages,
    )


# ---------------------------------------------------------------------------
# メモリ CRUD
# ---------------------------------------------------------------------------


@router.get("/me/memories", response_model=list[UserMemoryResponse])
async def list_memories(
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
) -> list[UserMemoryResponse]:
    """ユーザーのメモリ（自分について）を全件取得する。"""
    await _get_or_create_user(user_id, db)
    result = await db.execute(
        select(UserMemory)
        .where(UserMemory.user_id == user_id)
        .order_by(UserMemory.created_at)
    )
    items = result.scalars().all()
    return [
        UserMemoryResponse(
            id=item.id,
            content=item.content,
            source=item.source,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )
        for item in items
    ]


@router.post("/me/memories", status_code=201, response_model=UserMemoryResponse)
async def create_memory(
    body: CreateMemoryRequest,
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
) -> UserMemoryResponse:
    """メモリを追加する。"""
    await _get_or_create_user(user_id, db)
    now = _now_iso()
    memory = UserMemory(
        id=str(uuid.uuid4()),
        user_id=user_id,
        content=body.content,
        source="manual",
        created_at=now,
        updated_at=now,
    )
    db.add(memory)
    await db.commit()
    await db.refresh(memory)
    return UserMemoryResponse(
        id=memory.id,
        content=memory.content,
        source=memory.source,
        created_at=memory.created_at,
        updated_at=memory.updated_at,
    )


@router.put("/me/memories/{memory_id}", response_model=UserMemoryResponse)
async def update_memory(
    memory_id: str = Path(...),
    body: UpdateMemoryRequest = ...,
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
) -> UserMemoryResponse:
    """メモリを更新する。"""
    result = await db.execute(
        select(UserMemory).where(
            UserMemory.id == memory_id,
            UserMemory.user_id == user_id,
        )
    )
    memory = result.scalar_one_or_none()
    if memory is None:
        raise HTTPException(status_code=404, detail="メモリが見つかりません")

    memory.content = body.content
    memory.updated_at = _now_iso()
    await db.commit()
    return UserMemoryResponse(
        id=memory.id,
        content=memory.content,
        source=memory.source,
        created_at=memory.created_at,
        updated_at=memory.updated_at,
    )


@router.delete("/me/memories/{memory_id}", status_code=204)
async def delete_memory(
    memory_id: str = Path(...),
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """メモリを削除する。"""
    result = await db.execute(
        select(UserMemory).where(
            UserMemory.id == memory_id,
            UserMemory.user_id == user_id,
        )
    )
    memory = result.scalar_one_or_none()
    if memory is None:
        raise HTTPException(status_code=404, detail="メモリが見つかりません")
    await db.delete(memory)
    await db.commit()
    return Response(status_code=204)
