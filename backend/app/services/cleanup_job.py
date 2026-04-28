"""
ソフトデリート自動パージバックグラウンドジョブモジュール。
保持期限（デフォルト 30 日）を超えたソフトデリート済みドキュメントを
Qdrant・SQLite・ディスクから永続削除する。
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.infrastructure.config import config
from app.infrastructure.db import AsyncSessionLocal
from app.infrastructure import qdrant_client as qdrant
from app.models.database import Document, DocumentTag

logger = logging.getLogger(__name__)

# アプリケーション起動中に保持するスケジューラタスクの参照
_scheduler_task: asyncio.Task[None] | None = None


async def purge_expired_documents() -> int:
    """
    保持期限を超えたソフトデリート済みドキュメントを永続削除する。

    処理順序（1 ドキュメントごと）:
      1. Qdrant からベクトルを削除する（document_id フィルタ）。
      2. SQLite の document_tags レコードを削除する。
      3. SQLite の document レコードを削除する。
      4. ディスク上のアップロードファイルを削除する（存在する場合）。

    1 件の失敗は他の件の処理を妨げない。

    Returns:
        永続削除したドキュメントの件数。
    """
    retention_days = config.SOFT_DELETE_RETENTION_DAYS
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    cutoff_iso = cutoff.isoformat()

    logger.info(
        "purge_expired_documents: scanning for documents deleted before %s (retention=%d days)",
        cutoff_iso,
        retention_days,
    )

    purge_count = 0

    async with AsyncSessionLocal() as db:
        # deleted_at が NULL でなく、かつ cutoff より古いレコードを取得する。
        # deleted_at は TEXT 型（ISO 8601）で格納されているため文字列比較で期限判定する。
        result = await db.execute(
            select(Document).where(
                Document.deleted_at.is_not(None),
                Document.deleted_at <= cutoff_iso,
            )
        )
        expired_docs = list(result.scalars().all())

    logger.info(
        "purge_expired_documents: found %d expired document(s)", len(expired_docs)
    )

    for doc in expired_docs:
        doc_id = doc.id
        original_path = doc.original_path

        try:
            # ---- Step 1: Qdrant ベクトル削除 ----
            try:
                qdrant.delete_by_document_id(doc_id)
                logger.info("purge: deleted Qdrant vectors for document_id=%s", doc_id)
            except Exception:
                logger.exception(
                    "purge: failed to delete Qdrant vectors for document_id=%s (continuing)",
                    doc_id,
                )

            # ---- Step 2 & 3: SQLite から document_tags + document を削除 ----
            async with AsyncSessionLocal() as db:
                # document_tags を明示削除（cascade="all, delete-orphan" があるが
                # 明示的に削除することで確実性を高める）
                tags_result = await db.execute(
                    select(DocumentTag).where(DocumentTag.document_id == doc_id)
                )
                tags = list(tags_result.scalars().all())
                for tag in tags:
                    await db.delete(tag)

                # document レコードを削除
                doc_result = await db.execute(
                    select(Document).where(Document.id == doc_id)
                )
                doc_record = doc_result.scalar_one_or_none()
                if doc_record is not None:
                    await db.delete(doc_record)

                await db.commit()
                logger.info(
                    "purge: deleted SQLite records for document_id=%s (tags=%d)",
                    doc_id,
                    len(tags),
                )

            # ---- Step 4: ディスクファイル削除 ----
            if original_path and os.path.exists(original_path):
                try:
                    os.remove(original_path)
                    logger.info(
                        "purge: deleted file %s for document_id=%s",
                        original_path,
                        doc_id,
                    )
                except OSError:
                    logger.exception(
                        "purge: failed to delete file %s for document_id=%s (continuing)",
                        original_path,
                        doc_id,
                    )

            purge_count += 1
            logger.info("purge: successfully purged document_id=%s", doc_id)

        except Exception:
            logger.exception(
                "purge: unexpected error for document_id=%s, skipping this document",
                doc_id,
            )

    logger.info(
        "purge_expired_documents: completed, purged %d document(s)", purge_count
    )
    return purge_count


async def start_cleanup_scheduler() -> None:
    """
    1 日 1 回 purge_expired_documents を実行するスケジューラループ。

    アプリケーションの lifespan 起動時に asyncio.create_task で起動する。
    タスクは停止時に cancel して適切にクリーンアップする。
    """
    logger.info("start_cleanup_scheduler: cleanup scheduler started (interval=86400s)")

    while True:
        try:
            purged = await purge_expired_documents()
            logger.info("cleanup_scheduler: cycle complete, purged=%d", purged)
        except asyncio.CancelledError:
            logger.info("start_cleanup_scheduler: scheduler task cancelled, exiting")
            raise
        except Exception:
            logger.exception("cleanup_scheduler: unexpected error during purge cycle")

        try:
            # 24 時間待機（asyncio.CancelledError で中断可能）
            await asyncio.sleep(86400)
        except asyncio.CancelledError:
            logger.info("start_cleanup_scheduler: cancelled during sleep, exiting")
            raise


def get_scheduler_task() -> asyncio.Task[None] | None:
    """現在実行中のスケジューラタスクを返す。"""
    return _scheduler_task


def create_scheduler_task() -> asyncio.Task[None]:
    """
    スケジューラタスクを作成してモジュールレベルの参照に保持する。

    Returns:
        作成した asyncio.Task インスタンス。
    """
    global _scheduler_task
    _scheduler_task = asyncio.create_task(
        start_cleanup_scheduler(),
        name="cleanup_scheduler",
    )
    return _scheduler_task


def cancel_scheduler_task() -> None:
    """スケジューラタスクをキャンセルする。アプリケーション終了時に呼び出す。"""
    global _scheduler_task
    if _scheduler_task is not None and not _scheduler_task.done():
        _scheduler_task.cancel()
        logger.info("cancel_scheduler_task: cleanup scheduler task cancelled")
    _scheduler_task = None
