"""
ナレッジベース API エンドポイントの統合テスト。

インメモリ SQLite と httpx.AsyncClient を使用し、
Qdrant の呼び出しはモックで差し替える。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient

TEST_USER_ID = "user-kb-test-001"
HEADERS = {"X-User-Id": TEST_USER_ID}


# ---------------------------------------------------------------------------
# POST /api/knowledge-bases
# ---------------------------------------------------------------------------


class TestCreateKnowledgeBase:
    """ナレッジベース作成エンドポイントのテスト。"""

    @pytest.mark.asyncio
    async def test_create_knowledge_base(self, client: AsyncClient) -> None:
        """POST /api/knowledge-bases でナレッジベースが正常に作成される。"""
        payload = {
            "name": "テスト KB",
            "description": "説明文",
            "color": "#ff0000",
        }

        response = await client.post(
            "/api/knowledge-bases/",
            json=payload,
            headers=HEADERS,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "テスト KB"
        assert data["description"] == "説明文"
        assert data["color"] == "#ff0000"
        assert data["created_by"] == TEST_USER_ID
        assert "id" in data
        assert "created_at" in data
        assert "updated_at" in data
        assert data["document_count"] == 0
        assert data["is_favorite"] is False

    @pytest.mark.asyncio
    async def test_create_knowledge_base_default_color(self, client: AsyncClient) -> None:
        """color 未指定時はデフォルト色 #6366f1 が使われる。"""
        payload = {"name": "デフォルト色 KB"}

        response = await client.post(
            "/api/knowledge-bases/",
            json=payload,
            headers=HEADERS,
        )

        assert response.status_code == 201
        assert response.json()["color"] == "#6366f1"

    @pytest.mark.asyncio
    async def test_create_knowledge_base_missing_user_id(self, client: AsyncClient) -> None:
        """X-User-Id ヘッダーなしのリクエストは 422 または 400 を返す。"""
        response = await client.post(
            "/api/knowledge-bases/",
            json={"name": "KB"},
        )

        assert response.status_code in (400, 422)

    @pytest.mark.asyncio
    async def test_create_knowledge_base_empty_name(self, client: AsyncClient) -> None:
        """空文字の name は 422 バリデーションエラーになる。"""
        response = await client.post(
            "/api/knowledge-bases/",
            json={"name": ""},
            headers=HEADERS,
        )

        assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/knowledge-bases
# ---------------------------------------------------------------------------


class TestListKnowledgeBases:
    """ナレッジベース一覧取得エンドポイントのテスト。"""

    @pytest.mark.asyncio
    async def test_list_knowledge_bases_empty(self, client: AsyncClient) -> None:
        """ナレッジベースが存在しない場合は空リストが返る。"""
        response = await client.get("/api/knowledge-bases/", headers=HEADERS)

        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_list_knowledge_bases(self, client: AsyncClient) -> None:
        """作成したナレッジベースが一覧に含まれる。"""
        # 2件作成
        for i in range(2):
            await client.post(
                "/api/knowledge-bases/",
                json={"name": f"KB {i}"},
                headers=HEADERS,
            )

        response = await client.get("/api/knowledge-bases/", headers=HEADERS)

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        names = [d["name"] for d in data]
        assert "KB 0" in names
        assert "KB 1" in names

    @pytest.mark.asyncio
    async def test_list_knowledge_bases_order_desc(self, client: AsyncClient) -> None:
        """一覧は created_at の降順で返される。"""
        for name in ["First", "Second"]:
            await client.post(
                "/api/knowledge-bases/",
                json={"name": name},
                headers=HEADERS,
            )

        response = await client.get("/api/knowledge-bases/", headers=HEADERS)
        data = response.json()

        assert data[0]["name"] == "Second"
        assert data[1]["name"] == "First"


# ---------------------------------------------------------------------------
# GET /api/knowledge-bases/{id}
# ---------------------------------------------------------------------------


class TestGetKnowledgeBase:
    """ナレッジベース単件取得エンドポイントのテスト。"""

    @pytest.mark.asyncio
    async def test_get_knowledge_base(self, client: AsyncClient) -> None:
        """GET /api/knowledge-bases/{id} で作成済み KB が取得できる。"""
        create_resp = await client.post(
            "/api/knowledge-bases/",
            json={"name": "取得テスト KB", "description": "詳細"},
            headers=HEADERS,
        )
        kb_id = create_resp.json()["id"]

        # ルーターに GET /{id} が存在するか確認
        # knowledge_bases.py には個別取得エンドポイントがないため、
        # 一覧から ID 検索で代替する
        response = await client.get("/api/knowledge-bases/", headers=HEADERS)
        assert response.status_code == 200
        items = response.json()
        found = next((i for i in items if i["id"] == kb_id), None)
        assert found is not None
        assert found["name"] == "取得テスト KB"
        assert found["description"] == "詳細"


# ---------------------------------------------------------------------------
# PUT /api/knowledge-bases/{id}
# ---------------------------------------------------------------------------


class TestUpdateKnowledgeBase:
    """ナレッジベース更新エンドポイントのテスト。"""

    @pytest.mark.asyncio
    async def test_update_knowledge_base(self, client: AsyncClient) -> None:
        """PUT /api/knowledge-bases/{id} で名前・説明・色を更新できる。"""
        create_resp = await client.post(
            "/api/knowledge-bases/",
            json={"name": "旧名称", "description": "旧説明", "color": "#000000"},
            headers=HEADERS,
        )
        kb_id = create_resp.json()["id"]

        update_payload = {
            "name": "新名称",
            "description": "新説明",
            "color": "#ffffff",
        }
        response = await client.put(
            f"/api/knowledge-bases/{kb_id}",
            json=update_payload,
            headers=HEADERS,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "新名称"
        assert data["description"] == "新説明"
        assert data["color"] == "#ffffff"

    @pytest.mark.asyncio
    async def test_update_knowledge_base_partial(self, client: AsyncClient) -> None:
        """部分更新: 指定フィールドのみ変更され、未指定フィールドは保持される。"""
        create_resp = await client.post(
            "/api/knowledge-bases/",
            json={"name": "元の名前", "color": "#aabbcc"},
            headers=HEADERS,
        )
        kb_id = create_resp.json()["id"]

        response = await client.put(
            f"/api/knowledge-bases/{kb_id}",
            json={"name": "変更後の名前"},
            headers=HEADERS,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "変更後の名前"
        assert data["color"] == "#aabbcc"

    @pytest.mark.asyncio
    async def test_update_knowledge_base_not_found(self, client: AsyncClient) -> None:
        """存在しない KB の更新は 404 を返す。"""
        response = await client.put(
            "/api/knowledge-bases/nonexistent-id",
            json={"name": "新名称"},
            headers=HEADERS,
        )

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/knowledge-bases/{id}
# ---------------------------------------------------------------------------


class TestDeleteKnowledgeBase:
    """ナレッジベース削除エンドポイントのテスト。"""

    @pytest.mark.asyncio
    async def test_delete_knowledge_base(self, client: AsyncClient) -> None:
        """DELETE /api/knowledge-bases/{id} で KB が削除され 204 が返る。"""
        create_resp = await client.post(
            "/api/knowledge-bases/",
            json={"name": "削除対象 KB"},
            headers=HEADERS,
        )
        kb_id = create_resp.json()["id"]

        with patch(
            "app.routers.knowledge_bases.qdrant.delete_by_knowledge_base_id",
            MagicMock(),
        ):
            response = await client.delete(
                f"/api/knowledge-bases/{kb_id}",
                headers=HEADERS,
            )

        assert response.status_code == 204

        # 削除後は一覧から消えていること
        list_resp = await client.get("/api/knowledge-bases/", headers=HEADERS)
        items = list_resp.json()
        assert not any(i["id"] == kb_id for i in items)

    @pytest.mark.asyncio
    async def test_delete_knowledge_base_not_found(self, client: AsyncClient) -> None:
        """存在しない KB の削除は 404 を返す。"""
        with patch(
            "app.routers.knowledge_bases.qdrant.delete_by_knowledge_base_id",
            MagicMock(),
        ):
            response = await client.delete(
                "/api/knowledge-bases/nonexistent-id",
                headers=HEADERS,
            )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_calls_qdrant(self, client: AsyncClient) -> None:
        """削除時に Qdrant の delete_by_knowledge_base_id が呼び出される。"""
        create_resp = await client.post(
            "/api/knowledge-bases/",
            json={"name": "Qdrant テスト KB"},
            headers=HEADERS,
        )
        kb_id = create_resp.json()["id"]

        mock_qdrant_delete = MagicMock()
        with patch(
            "app.routers.knowledge_bases.qdrant.delete_by_knowledge_base_id",
            mock_qdrant_delete,
        ):
            await client.delete(
                f"/api/knowledge-bases/{kb_id}",
                headers=HEADERS,
            )

        mock_qdrant_delete.assert_called_once_with(kb_id)
