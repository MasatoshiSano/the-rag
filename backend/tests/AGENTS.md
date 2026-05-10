<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-10 | Updated: 2026-05-10 -->

# tests

## Purpose
バックエンドの pytest テストスイート。インメモリ SQLite（aiosqlite + `:memory:`）と外部依存スタブを組み合わせ、ネットワーク非接続で完結する。

## Key Files
| File | Description |
|------|-------------|
| `conftest.py` | `qdrant_client` / `boto3` / `app.infrastructure.{db,bedrock_client,qdrant_client,master_cache}` のスタブ登録、インメモリ DB の `db_session` フィクスチャ、lifespan を切った FastAPI テスト用 `client` フィクスチャ |
| `test_api_knowledge_bases.py` | KB の CRUD・お気に入り API テスト |
| `test_api_users.py` | `/users/me` 設定・プロファイル・メモリ API テスト |
| `test_cleanup_job.py` | ソフトデリート自動パージのスケジューラロジックテスト |
| `test_folder_scanner.py` | Windows パス → コンテナパス変換とスキャンのテスト |
| `test_output_formatter.py` | クエリ結果 → 構造化出力変換のテスト |
| `test_user_profile.py` | チャット履歴 → 行動プロファイル更新のテスト |
| `__init__.py` | パッケージマーカー |

## For AI Agents

### Working In This Directory
- `_install_stubs()` が **テスト収集前** に呼び出されることに依存している。新しい外部依存モジュール（boto3 系の追加機能など）を使い始めたらこの関数にもスタブを追加する。
- テスト用 `client` フィクスチャは `main.py` の `lifespan` を `_noop_lifespan` で差し替え、`init_db` / `load_master_cache` をスキップする。実 lifespan の挙動を検証したい場合は別フィクスチャを書く。
- `test_app.include_router(...)` のリストに新ルーターを追加し忘れると 404 になる。`main.py:create_app` と二重管理になっているので同期を保つ。
- 各テストは独立した `:memory:` エンジンを使うため、テスト間のデータ汚染はない。

### Testing Requirements
- 実行: `cd backend && pytest`。デフォルト引数で十分。
- 非同期テストは `pytest_asyncio.fixture` + `async def test_...` スタイル。`pytest_plugins = ["pytest_asyncio"]` 済み。
- Bedrock 呼び出しを伴うサービスを新規にテストする場合は、`bedrock_stub.<関数名> = AsyncMock(return_value=...)` で振る舞いを設定してから対象関数を呼ぶ。

### Common Patterns
- `httpx.AsyncClient(transport=ASGITransport(app=test_app), base_url="http://testserver")` で FastAPI を直接叩く。
- `headers={"X-User-Id": "..."}` で匿名ユーザーを偽装。

## Dependencies

### Internal
- `app/*` — テスト対象すべて

### External
- `pytest`, `pytest-asyncio`, `httpx`, `moto`

<!-- MANUAL: -->
