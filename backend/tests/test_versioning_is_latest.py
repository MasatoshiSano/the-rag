"""バージョニング (is_latest 反転) の回帰テスト。

旧バージョンドキュメントの Qdrant ベクトルが新バージョン indexing 時に
`is_latest=False` へソフトデプリケートされることを保証する。

外部サービス (Qdrant / Bedrock) はモックで差し替え、実機接続は要求しない。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
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
        name="バージョニングテスト KB",
        description=None,
        color="#6366f1",
        created_by=None,
        created_at=now,
        updated_at=now,
    )


def _make_document(
    doc_id: str,
    kb_id: str,
    *,
    parent_document_id: str | None = None,
    converted_md: str | None = "テスト本文",
    status: str = "confirmed",
    version: int = 1,
) -> Document:
    now = datetime.now(timezone.utc).isoformat()
    return Document(
        id=doc_id,
        knowledge_base_id=kb_id,
        filename=f"{doc_id}.md",
        file_type="md",
        original_path=f"/tmp/{doc_id}.md",
        converted_md=converted_md,
        version=version,
        parent_document_id=parent_document_id,
        status=status,
        retry_count=0,
        deleted_at=None,
        uploaded_at=now,
    )


# ---------------------------------------------------------------------------
# mark_previous_versions_not_latest 単体テスト
# ---------------------------------------------------------------------------


class TestMarkPreviousVersionsNotLatest:
    """`embedder.mark_previous_versions_not_latest` の Qdrant 呼び出しを検証する。"""

    def test_empty_list_is_noop(self) -> None:
        """空リストの場合、Qdrant クライアントを呼ばずに即 return する。"""
        from app.services import embedder

        with patch.object(
            embedder.qdrant_infra, "get_qdrant_client"
        ) as mock_get_client:
            embedder.mark_previous_versions_not_latest([])

        mock_get_client.assert_not_called()

    def test_calls_set_payload_with_match_any_filter(self) -> None:
        """previous_document_ids を含むフィルタで set_payload が呼ばれる。"""
        from app.services import embedder

        mock_client = MagicMock()
        previous_ids = ["doc-v1", "doc-v0"]

        with patch.object(
            embedder.qdrant_infra, "get_qdrant_client", return_value=mock_client
        ):
            embedder.mark_previous_versions_not_latest(previous_ids)

        # set_payload が 1 回呼ばれていること
        assert mock_client.set_payload.call_count == 1
        kwargs = mock_client.set_payload.call_args.kwargs

        # is_latest=False に更新する payload
        assert kwargs["payload"] == {"is_latest": False}

        # フィルタが渡されている (Filter / FieldCondition / MatchAny は qdrant_client スタブ
        # 由来の MagicMock のため、直接の構造比較ではなく呼び出された事実だけを保証する)
        assert "points" in kwargs


# ---------------------------------------------------------------------------
# _collect_previous_version_ids のサイクル耐性テスト
# ---------------------------------------------------------------------------


class TestCollectPreviousVersionIds:
    """`documents._collect_previous_version_ids` の祖先収集ロジックを検証する。"""

    @pytest.mark.asyncio
    async def test_no_parent_returns_empty(
        self, db_session: AsyncSession
    ) -> None:
        """親が無いドキュメントの祖先リストは空。"""
        from app.routers.documents import _collect_previous_version_ids

        kb = _make_knowledge_base("kb-ver-001")
        db_session.add(kb)
        doc = _make_document("doc-root", "kb-ver-001", parent_document_id=None)
        db_session.add(doc)
        await db_session.flush()

        ancestors = await _collect_previous_version_ids("doc-root", db_session)
        assert ancestors == []

    @pytest.mark.asyncio
    async def test_linear_chain_collects_all_ancestors(
        self, db_session: AsyncSession
    ) -> None:
        """v1 ← v2 ← v3 の線形チェーンで v3 から祖先 [v2, v1] を収集する。"""
        from app.routers.documents import _collect_previous_version_ids

        kb = _make_knowledge_base("kb-ver-002")
        db_session.add(kb)
        v1 = _make_document("doc-v1", "kb-ver-002", parent_document_id=None, version=1)
        v2 = _make_document(
            "doc-v2", "kb-ver-002", parent_document_id="doc-v1", version=2
        )
        v3 = _make_document(
            "doc-v3", "kb-ver-002", parent_document_id="doc-v2", version=3
        )
        db_session.add_all([v1, v2, v3])
        await db_session.flush()

        ancestors = await _collect_previous_version_ids("doc-v3", db_session)
        assert ancestors == ["doc-v2", "doc-v1"]

    @pytest.mark.asyncio
    async def test_cycle_does_not_loop_forever(
        self, db_session: AsyncSession
    ) -> None:
        """循環参照 A→B→A があっても visited セットで無限ループを避ける。

        通常運用では生成されない病理的データだが、移行作業や手動修正で
        発生し得るため防御的に検証する。
        """
        from app.routers.documents import _collect_previous_version_ids

        kb = _make_knowledge_base("kb-ver-003")
        db_session.add(kb)
        # 先に B (parent=A) を作成し、後で A.parent を B に書き換えてサイクルを成立させる
        # （SQLite の FK 検証はデフォルト無効なので通る）
        a = _make_document("doc-a", "kb-ver-003", parent_document_id=None)
        b = _make_document("doc-b", "kb-ver-003", parent_document_id="doc-a")
        db_session.add_all([a, b])
        await db_session.flush()

        a.parent_document_id = "doc-b"
        await db_session.flush()

        ancestors = await _collect_previous_version_ids("doc-b", db_session)
        # サイクルで無限ループせず、有限のリストで返ること
        assert "doc-a" in ancestors
        # visited セットにより同じ ID は一度だけしか登場しないこと
        assert len(ancestors) == len(set(ancestors))


# ---------------------------------------------------------------------------
# _run_post_tag_pipeline 経由の v1 → v2 → confirm で is_latest 反転を検証
# ---------------------------------------------------------------------------


class TestPostTagPipelineFlipsIsLatest:
    """`_run_post_tag_pipeline` 内で旧バージョンの is_latest=False 切替が発火することを確認する。"""

    @pytest.mark.asyncio
    async def test_v2_indexing_invalidates_v1(
        self, db_session: AsyncSession
    ) -> None:
        """v2 の確定パイプライン実行時に v1 の document_id を含むリストで
        `mark_previous_versions_not_latest` が呼ばれる。
        """
        kb = _make_knowledge_base("kb-pipeline-001")
        db_session.add(kb)
        v1 = _make_document("doc-v1", "kb-pipeline-001", parent_document_id=None, version=1)
        v2 = _make_document(
            "doc-v2",
            "kb-pipeline-001",
            parent_document_id="doc-v1",
            version=2,
        )
        db_session.add_all([v1, v2])
        await db_session.flush()

        # 同じ db_session を AsyncSessionLocal() の代わりに返す
        @asynccontextmanager
        async def _mock_session_factory():
            yield db_session

        # チャンク・埋め込み・upsert・無効化の各処理をモック化して呼び出しを観測する
        mock_chunk_document = MagicMock(return_value=[])
        mock_embed_chunks = AsyncMock(return_value=[])
        mock_upsert = MagicMock()
        mock_mark_prev = MagicMock()

        with (
            patch(
                "app.routers.documents.AsyncSessionLocal",
                side_effect=_mock_session_factory,
            ),
            patch(
                "app.services.chunker.chunk_document",
                mock_chunk_document,
            ),
            patch(
                "app.services.embedder.embed_chunks",
                mock_embed_chunks,
            ),
            patch(
                "app.services.embedder.upsert_embedded_chunks",
                mock_upsert,
            ),
            patch(
                "app.services.embedder.mark_previous_versions_not_latest",
                mock_mark_prev,
            ),
        ):
            from app.routers.documents import _run_post_tag_pipeline

            await _run_post_tag_pipeline("doc-v2")

        # v1 の ID を含むリストで mark_previous_versions_not_latest が呼ばれたこと
        mock_mark_prev.assert_called_once()
        call_args = mock_mark_prev.call_args.args
        assert len(call_args) == 1
        previous_ids = call_args[0]
        assert "doc-v1" in previous_ids

        # 新バージョン (v2) は is_latest=True で upsert される
        mock_upsert.assert_called_once()
        upsert_kwargs = mock_upsert.call_args.kwargs
        assert upsert_kwargs["document_id"] == "doc-v2"
        assert upsert_kwargs["is_latest"] is True

        # v2 のステータスが indexed に遷移していること
        result = await db_session.execute(
            select(Document).where(Document.id == "doc-v2")
        )
        v2_after = result.scalar_one()
        assert v2_after.status == "indexed"

    @pytest.mark.asyncio
    async def test_initial_v1_indexing_does_not_call_mark_prev(
        self, db_session: AsyncSession
    ) -> None:
        """v1 (parent なし) の初回確定では旧バージョン無効化は呼ばれない。"""
        kb = _make_knowledge_base("kb-pipeline-002")
        db_session.add(kb)
        v1 = _make_document(
            "doc-only-v1",
            "kb-pipeline-002",
            parent_document_id=None,
            version=1,
        )
        db_session.add(v1)
        await db_session.flush()

        @asynccontextmanager
        async def _mock_session_factory():
            yield db_session

        mock_mark_prev = MagicMock()

        with (
            patch(
                "app.routers.documents.AsyncSessionLocal",
                side_effect=_mock_session_factory,
            ),
            patch(
                "app.services.chunker.chunk_document",
                MagicMock(return_value=[]),
            ),
            patch(
                "app.services.embedder.embed_chunks",
                AsyncMock(return_value=[]),
            ),
            patch(
                "app.services.embedder.upsert_embedded_chunks",
                MagicMock(),
            ),
            patch(
                "app.services.embedder.mark_previous_versions_not_latest",
                mock_mark_prev,
            ),
        ):
            from app.routers.documents import _run_post_tag_pipeline

            await _run_post_tag_pipeline("doc-only-v1")

        # 親が無いため旧バージョン無効化は呼ばれない
        mock_mark_prev.assert_not_called()
