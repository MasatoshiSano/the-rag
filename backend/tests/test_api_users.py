"""
ユーザー API エンドポイントの統合テスト。

インメモリ SQLite と httpx.AsyncClient を使用し、
ユーザーの自動生成・設定更新・固定語録・行動プロファイルをテストする。
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

TEST_USER_ID = "user-api-test-001"
HEADERS = {"X-User-Id": TEST_USER_ID}


# ---------------------------------------------------------------------------
# GET /api/users/me
# ---------------------------------------------------------------------------


class TestGetMe:
    """ユーザー取得エンドポイントのテスト。"""

    @pytest.mark.asyncio
    async def test_get_me_creates_user(self, client: AsyncClient) -> None:
        """GET /api/users/me で新規ユーザーが自動生成され、デフォルト値が返る。"""
        response = await client.get("/api/users/me", headers=HEADERS)

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == TEST_USER_ID
        assert data["nickname"] is None
        assert data["rerank_enabled"] is False
        assert data["hybrid_search_enabled"] is True
        assert data["response_mode"] == "detailed"
        assert "created_at" in data
        assert "updated_at" in data

    @pytest.mark.asyncio
    async def test_get_me_idempotent(self, client: AsyncClient) -> None:
        """同じ X-User-Id で複数回 GET しても同一レコードが返る。"""
        resp1 = await client.get("/api/users/me", headers=HEADERS)
        resp2 = await client.get("/api/users/me", headers=HEADERS)

        assert resp1.json()["id"] == resp2.json()["id"]
        assert resp1.json()["created_at"] == resp2.json()["created_at"]

    @pytest.mark.asyncio
    async def test_get_me_missing_header(self, client: AsyncClient) -> None:
        """X-User-Id ヘッダーなしのリクエストは 422 を返す。"""
        response = await client.get("/api/users/me")

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_me_empty_header(self, client: AsyncClient) -> None:
        """X-User-Id が空文字の場合は 400 を返す。"""
        response = await client.get("/api/users/me", headers={"X-User-Id": "   "})

        assert response.status_code == 400


# ---------------------------------------------------------------------------
# PUT /api/users/me/settings
# ---------------------------------------------------------------------------


class TestUpdateSettings:
    """ユーザー設定更新エンドポイントのテスト。"""

    @pytest.mark.asyncio
    async def test_update_settings(self, client: AsyncClient) -> None:
        """PUT /api/users/me/settings で設定が正しく更新される。"""
        # 先にユーザーを作成する
        await client.get("/api/users/me", headers=HEADERS)

        payload = {
            "nickname": "テストユーザー",
            "rerank_enabled": True,
            "hybrid_search_enabled": True,
            "response_mode": "detailed",
        }
        response = await client.put(
            "/api/users/me/settings",
            json=payload,
            headers=HEADERS,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["nickname"] == "テストユーザー"
        assert data["rerank_enabled"] is True
        assert data["hybrid_search_enabled"] is True
        assert data["response_mode"] == "detailed"

    @pytest.mark.asyncio
    async def test_update_settings_partial(self, client: AsyncClient) -> None:
        """部分更新: 未指定フィールドは変更されない。"""
        await client.get("/api/users/me", headers=HEADERS)

        # nickname のみ更新
        response = await client.put(
            "/api/users/me/settings",
            json={"nickname": "部分更新"},
            headers=HEADERS,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["nickname"] == "部分更新"
        assert data["rerank_enabled"] is False  # デフォルト値が保持される

    @pytest.mark.asyncio
    async def test_update_settings_invalid_response_mode(
        self, client: AsyncClient
    ) -> None:
        """不正な response_mode は 422 バリデーションエラーになる。"""
        await client.get("/api/users/me", headers=HEADERS)

        response = await client.put(
            "/api/users/me/settings",
            json={"response_mode": "invalid_mode"},
            headers=HEADERS,
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_update_settings_creates_user_if_not_exists(
        self, client: AsyncClient
    ) -> None:
        """ユーザーが未作成の場合でも設定更新でユーザーが自動生成される。"""
        response = await client.put(
            "/api/users/me/settings",
            json={"nickname": "新規ユーザー"},
            headers=HEADERS,
        )

        assert response.status_code == 200
        assert response.json()["nickname"] == "新規ユーザー"


# ---------------------------------------------------------------------------
# GET /api/users/me/behavior
# ---------------------------------------------------------------------------


class TestGetBehavior:
    """ユーザー行動プロファイル取得エンドポイントのテスト。"""

    @pytest.mark.asyncio
    async def test_get_behavior(self, client: AsyncClient) -> None:
        """GET /api/users/me/behavior で行動プロファイルが返る（初期状態は空）。"""
        await client.get("/api/users/me", headers=HEADERS)

        response = await client.get("/api/users/me/behavior", headers=HEADERS)

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == TEST_USER_ID
        assert data["frequent_lines"] == []
        assert data["frequent_categories"] == []
        assert data["recent_context"] is None
        assert data["total_sessions"] == 0
        assert data["total_messages"] == 0

    @pytest.mark.asyncio
    async def test_get_behavior_creates_user_if_not_exists(
        self, client: AsyncClient
    ) -> None:
        """ユーザーが存在しない場合でも行動プロファイルが返る（ユーザーが自動生成される）。"""
        response = await client.get("/api/users/me/behavior", headers=HEADERS)

        assert response.status_code == 200
        assert response.json()["user_id"] == TEST_USER_ID

    @pytest.mark.asyncio
    async def test_get_behavior_missing_header(self, client: AsyncClient) -> None:
        """X-User-Id ヘッダーなしのリクエストは 422 を返す。"""
        response = await client.get("/api/users/me/behavior")

        assert response.status_code == 422
