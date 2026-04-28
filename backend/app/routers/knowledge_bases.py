"""
ナレッジベース管理ルーターモジュール。
ナレッジベースの作成・管理・お気に入り機能の API エンドポイントを提供する。

X-User-Id ヘッダーによるユーザー識別を使用する。
削除時は SQLite のカスケード削除と Qdrant ベクトルの両方を削除する。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db import get_db
from app.infrastructure import qdrant_client as qdrant
from app.models.database import (
    Document,
    KnowledgeBase,
    KnowledgeBaseFavorite,
    User,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge-bases", tags=["knowledge-bases"])

# ---------------------------------------------------------------------------
# Pydantic スキーマ
# ---------------------------------------------------------------------------


class KnowledgeBaseResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    color: str
    created_by: Optional[str]
    created_at: str
    updated_at: str
    document_count: int = 0
    is_favorite: bool = False

    model_config = {"from_attributes": True}


class CreateKnowledgeBaseRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=1000)
    color: str = Field(default="#6366f1", max_length=50)


class UpdateKnowledgeBaseRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=1000)
    color: Optional[str] = Field(default=None, max_length=50)


class FavoriteResponse(BaseModel):
    knowledge_base_id: str
    user_id: str
    created_at: str


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


def _now_iso() -> str:
    """現在時刻を UTC ISO 8601 文字列で返す。"""
    return datetime.now(UTC).isoformat()


async def _get_kb_or_404(kb_id: str, db: AsyncSession) -> KnowledgeBase:
    """
    ナレッジベースを取得する。存在しない場合は 404 を送出する。

    Args:
        kb_id: 対象ナレッジベースの ID。
        db: 非同期データベースセッション。

    Returns:
        KnowledgeBase ORM インスタンス。

    Raises:
        HTTPException: ナレッジベースが見つからない場合。
    """
    result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    kb = result.scalar_one_or_none()
    if kb is None:
        raise HTTPException(status_code=404, detail=f"KnowledgeBase {kb_id} not found")
    return kb


async def _get_document_count(kb_id: str, db: AsyncSession) -> int:
    """指定ナレッジベースのドキュメント数（論理削除除外）を返す。"""
    result = await db.execute(
        select(func.count(Document.id)).where(
            Document.knowledge_base_id == kb_id,
            Document.deleted_at.is_(None),
        )
    )
    return result.scalar_one() or 0


async def _is_favorite(kb_id: str, user_id: str, db: AsyncSession) -> bool:
    """指定ユーザーがナレッジベースをお気に入り登録しているか確認する。"""
    result = await db.execute(
        select(KnowledgeBaseFavorite).where(
            KnowledgeBaseFavorite.knowledge_base_id == kb_id,
            KnowledgeBaseFavorite.user_id == user_id,
        )
    )
    return result.scalar_one_or_none() is not None


async def _kb_to_response(
    kb: KnowledgeBase,
    user_id: str,
    db: AsyncSession,
) -> KnowledgeBaseResponse:
    doc_count = await _get_document_count(kb.id, db)
    favorite = await _is_favorite(kb.id, user_id, db)
    return KnowledgeBaseResponse(
        id=kb.id,
        name=kb.name,
        description=kb.description,
        color=kb.color,
        created_by=kb.created_by,
        created_at=kb.created_at,
        updated_at=kb.updated_at,
        document_count=doc_count,
        is_favorite=favorite,
    )


async def _ensure_user_exists(user_id: str, db: AsyncSession) -> None:
    """
    ユーザーが DB に存在することを確認する。
    存在しない場合はデフォルト設定で新規作成する（users ルーターと共通の動作）。
    """
    result = await db.execute(select(User).where(User.id == user_id))
    if result.scalar_one_or_none() is None:
        now = _now_iso()
        user = User(
            id=user_id,
            nickname=None,
            rerank_enabled=0,
            hybrid_search_enabled=1,
            retrieval_count=20,
            response_mode="detailed",
            created_at=now,
            updated_at=now,
        )
        db.add(user)
        await db.flush()
        logger.info("Auto-created user during KB operation: %s", user_id)


# ---------------------------------------------------------------------------
# エンドポイント
# ---------------------------------------------------------------------------


@router.post("/", status_code=201, response_model=KnowledgeBaseResponse)
async def create_knowledge_base(
    body: CreateKnowledgeBaseRequest,
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
) -> KnowledgeBaseResponse:
    """
    新しいナレッジベースを作成する。
    created_by は X-User-Id ヘッダーから自動設定される。

    Args:
        body: name / description / color を含むリクエストボディ。
    """
    await _ensure_user_exists(user_id, db)

    now = _now_iso()
    kb = KnowledgeBase(
        id=str(uuid4()),
        name=body.name,
        description=body.description,
        color=body.color,
        created_by=user_id,
        created_at=now,
        updated_at=now,
    )
    db.add(kb)
    await db.flush()

    return await _kb_to_response(kb, user_id, db)


@router.get("/", response_model=list[KnowledgeBaseResponse])
async def list_knowledge_bases(
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
) -> list[KnowledgeBaseResponse]:
    """
    全ナレッジベースを作成日時の降順で取得する。
    各エントリにドキュメント数とお気に入りフラグを付与する。
    """
    result = await db.execute(
        select(KnowledgeBase).order_by(KnowledgeBase.created_at.desc())
    )
    kbs = result.scalars().all()
    return [await _kb_to_response(kb, user_id, db) for kb in kbs]


@router.get("/favorites", response_model=list[KnowledgeBaseResponse])
async def list_favorite_knowledge_bases(
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
) -> list[KnowledgeBaseResponse]:
    """
    現在のユーザーがお気に入り登録したナレッジベース一覧をお気に入り登録日時の降順で取得する。
    """
    result = await db.execute(
        select(KnowledgeBase)
        .join(
            KnowledgeBaseFavorite,
            KnowledgeBaseFavorite.knowledge_base_id == KnowledgeBase.id,
        )
        .where(KnowledgeBaseFavorite.user_id == user_id)
        .order_by(KnowledgeBaseFavorite.created_at.desc())
    )
    kbs = result.scalars().all()
    return [await _kb_to_response(kb, user_id, db) for kb in kbs]


@router.put("/{id}", status_code=200, response_model=KnowledgeBaseResponse)
async def update_knowledge_base(
    id: str = Path(..., description="ナレッジベース ID"),
    body: UpdateKnowledgeBaseRequest = UpdateKnowledgeBaseRequest(),
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
) -> KnowledgeBaseResponse:
    """
    指定ナレッジベースの名前・説明・カラーを更新する。
    未指定フィールドは変更しない。

    Args:
        id: 更新対象ナレッジベースの ID。
        body: 更新するフィールドを含むリクエストボディ。
    """
    kb = await _get_kb_or_404(id, db)

    if body.name is not None:
        kb.name = body.name
    if body.description is not None:
        kb.description = body.description
    if body.color is not None:
        kb.color = body.color

    kb.updated_at = _now_iso()
    await db.flush()

    return await _kb_to_response(kb, user_id, db)


@router.delete("/{id}", status_code=204, response_class=Response)
async def delete_knowledge_base(
    id: str = Path(..., description="ナレッジベース ID"),
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_user_id),
) -> Response:
    """
    指定ナレッジベースをカスケード削除する。

    削除順序:
      1. Qdrant から該当ナレッジベースの全ベクトルを削除する。
      2. SQLite から KnowledgeBase レコードを削除する（ORM カスケードにより
         documents / document_tags / favorites / sessions も連鎖削除される）。

    Args:
        id: 削除対象ナレッジベースの ID。
    """
    kb = await _get_kb_or_404(id, db)

    # 1. Qdrant ベクトルを削除（同期呼び出し）
    try:
        qdrant.delete_by_knowledge_base_id(id)
        logger.info("Deleted Qdrant vectors for knowledge_base_id=%s", id)
    except Exception:
        logger.exception(
            "Failed to delete Qdrant vectors for knowledge_base_id=%s; proceeding with DB deletion",
            id,
        )

    # 2. ORM カスケードで documents / document_tags / favorites / sessions を削除
    await db.delete(kb)
    logger.info("Deleted knowledge base id=%s", id)
    return Response(status_code=204)


@router.post("/{id}/favorite", status_code=201, response_model=FavoriteResponse)
async def add_favorite(
    id: str = Path(..., description="ナレッジベース ID"),
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
) -> FavoriteResponse:
    """
    指定ナレッジベースをお気に入りに追加する。
    既にお気に入り登録済みの場合は 409 を返す。

    Args:
        id: 対象ナレッジベースの ID。
    """
    await _get_kb_or_404(id, db)
    await _ensure_user_exists(user_id, db)

    dup_result = await db.execute(
        select(KnowledgeBaseFavorite).where(
            KnowledgeBaseFavorite.knowledge_base_id == id,
            KnowledgeBaseFavorite.user_id == user_id,
        )
    )
    if dup_result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=409,
            detail=f"KnowledgeBase {id} is already in favorites",
        )

    now = _now_iso()
    favorite = KnowledgeBaseFavorite(
        user_id=user_id,
        knowledge_base_id=id,
        created_at=now,
    )
    db.add(favorite)
    await db.flush()

    return FavoriteResponse(
        knowledge_base_id=id,
        user_id=user_id,
        created_at=now,
    )


@router.delete("/{id}/favorite", status_code=204, response_class=Response)
async def remove_favorite(
    id: str = Path(..., description="ナレッジベース ID"),
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    指定ナレッジベースをお気に入りから削除する。
    お気に入り登録されていない場合は 404 を返す。

    Args:
        id: 対象ナレッジベースの ID。
    """
    result = await db.execute(
        select(KnowledgeBaseFavorite).where(
            KnowledgeBaseFavorite.knowledge_base_id == id,
            KnowledgeBaseFavorite.user_id == user_id,
        )
    )
    favorite = result.scalar_one_or_none()
    if favorite is None:
        raise HTTPException(
            status_code=404,
            detail=f"KnowledgeBase {id} is not in favorites",
        )

    await db.delete(favorite)
    logger.info("Removed favorite: user_id=%s kb_id=%s", user_id, id)
    return Response(status_code=204)
