"""
cleanup_job サービスのユニットテスト。

purge_expired_documents のロジックをインメモリ SQLite で検証する。
Qdrant 呼び出しはモックで差し替える。
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import Document, KnowledgeBase


# ---------------------------------------------------------------------------
# テストデータ作成ヘルパー
# ---------------------------------------------------------------------------


def _make_knowledge_base(kb_id: str) -> KnowledgeBase:
    now = datetime.now(timezone.utc).isoformat()
    return KnowledgeBase(
        id=kb_id,
        name="テスト KB",
        description=None,
        color="#6366f1",
        created_by=None,
        created_at=now,
        updated_at=now,
    )


def _make_document(
    doc_id: str,
    kb_id: str,
    deleted_at: str | None = None,
) -> Document:
    now = datetime.now(timezone.utc).isoformat()
    return Document(
        id=doc_id,
        knowledge_base_id=kb_id,
        filename="test.pdf",
        file_type="pdf",
        original_path="/tmp/test.pdf",
        status="indexed",
        retry_count=0,
        deleted_at=deleted_at,
        uploaded_at=now,
    )


# ---------------------------------------------------------------------------
# purge_expired_documents のテスト
# ---------------------------------------------------------------------------


class TestPurgeExpiredDocuments:
    """purge_expired_documents 関数のテスト。"""

    @pytest.mark.asyncio
    async def test_purge_no_expired_documents(self, db_session: AsyncSession) -> None:
        """削除対象ドキュメントが存在しない場合、パージ件数は 0 になる。"""
        kb = _make_knowledge_base("kb-001")
        db_session.add(kb)
        # deleted_at が None のドキュメント（論理削除されていない）
        doc = _make_document("doc-001", "kb-001", deleted_at=None)
        db_session.add(doc)
        await db_session.flush()

        # AsyncSessionLocal をテスト用セッションで差し替える
        from unittest.mock import AsyncMock, patch
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _mock_session():
            yield db_session

        with (
            patch("app.services.cleanup_job.AsyncSessionLocal", side_effect=_mock_session),
            patch("app.services.cleanup_job.qdrant") as mock_qdrant,
        ):
            from app.services.cleanup_job import purge_expired_documents

            count = await purge_expired_documents()

        assert count == 0

    @pytest.mark.asyncio
    async def test_purge_expired_document(self, db_session: AsyncSession) -> None:
        """30日以上前に論理削除されたドキュメントが永続削除される。"""
        kb = _make_knowledge_base("kb-002")
        db_session.add(kb)

        # 31日前に削除済みのドキュメント
        old_deleted_at = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
        doc = _make_document("doc-expired", "kb-002", deleted_at=old_deleted_at)
        db_session.add(doc)
        await db_session.flush()

        call_count = 0

        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _mock_session_factory():
            nonlocal call_count
            call_count += 1
            yield db_session

        # original_path="/tmp/test.pdf" は UPLOAD_DIR (/app/uploads) 外のため、
        # safe_remove_within は自然に False を返してファイル削除をスキップする。
        # cleanup_job からは `import os` を撤去済 (Task E) のため os.path をパッチしない。
        with (
            patch("app.services.cleanup_job.AsyncSessionLocal", side_effect=_mock_session_factory),
            patch("app.services.cleanup_job.qdrant") as mock_qdrant,
            patch("app.services.cleanup_job.safe_remove_within", return_value=False),
        ):
            mock_qdrant.delete_by_document_id = MagicMock()

            from app.services.cleanup_job import purge_expired_documents

            count = await purge_expired_documents()

        assert count == 1
        mock_qdrant.delete_by_document_id.assert_called_once_with("doc-expired")

        # DB からドキュメントが削除されていること
        result = await db_session.execute(
            select(Document).where(Document.id == "doc-expired")
        )
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_purge_recent_document_not_deleted(self, db_session: AsyncSession) -> None:
        """保持期間内（例：1日前）に論理削除されたドキュメントは削除されない。"""
        kb = _make_knowledge_base("kb-003")
        db_session.add(kb)

        # 1日前に削除済み（保持期間 30日以内）
        recent_deleted_at = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        doc = _make_document("doc-recent", "kb-003", deleted_at=recent_deleted_at)
        db_session.add(doc)
        await db_session.flush()

        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _mock_session_factory():
            yield db_session

        with (
            patch("app.services.cleanup_job.AsyncSessionLocal", side_effect=_mock_session_factory),
            patch("app.services.cleanup_job.qdrant") as mock_qdrant,
        ):
            mock_qdrant.delete_by_document_id = MagicMock()

            from app.services.cleanup_job import purge_expired_documents

            count = await purge_expired_documents()

        assert count == 0
        mock_qdrant.delete_by_document_id.assert_not_called()

        # DB にドキュメントが残存していること
        result = await db_session.execute(
            select(Document).where(Document.id == "doc-recent")
        )
        assert result.scalar_one_or_none() is not None


# ---------------------------------------------------------------------------
# スケジューラタスクの生成・キャンセルテスト
# ---------------------------------------------------------------------------


class TestSchedulerTaskCreationAndCancellation:
    """スケジューラタスクのライフサイクルテスト。"""

    @pytest.mark.asyncio
    async def test_scheduler_task_creation_and_cancellation(self) -> None:
        """
        create_scheduler_task でタスクが生成され、
        cancel_scheduler_task でキャンセルされること。
        """
        # purge_expired_documents が実行されないよう即座に sleep するモックを使う
        async def _mock_scheduler() -> None:
            await asyncio.sleep(9999)

        with patch(
            "app.services.cleanup_job.start_cleanup_scheduler",
            side_effect=_mock_scheduler,
        ):
            from app.services.cleanup_job import (
                cancel_scheduler_task,
                create_scheduler_task,
                get_scheduler_task,
            )

            # タスクを生成する
            task = create_scheduler_task()
            assert task is not None
            assert not task.done()
            assert get_scheduler_task() is task

            # タスクをキャンセルする
            cancel_scheduler_task()
            # キャンセル後は参照が None になる
            assert get_scheduler_task() is None

            # タスクが CancelledError で終了するまで待つ
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

    @pytest.mark.asyncio
    async def test_cancel_scheduler_task_when_no_task(self) -> None:
        """タスクが存在しない状態でキャンセルを呼び出してもエラーにならない。"""
        import app.services.cleanup_job as cleanup_module

        # 事前にタスク参照を None にする
        original = cleanup_module._scheduler_task
        cleanup_module._scheduler_task = None

        try:
            cleanup_module.cancel_scheduler_task()  # 例外が発生しないこと
        finally:
            cleanup_module._scheduler_task = original
