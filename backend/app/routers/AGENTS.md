<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-10 | Updated: 2026-05-10 -->

# routers

## Purpose
FastAPI の HTTP エンドポイント定義。すべてのルーターは `main.py:create_app` で `prefix="/api"` を付けて登録される。匿名認証は `X-User-Id` ヘッダー、外部連携は `X-API-Key` ヘッダーで識別する。

## Key Files
| File | Description |
|------|-------------|
| `chat.py` | RAG チャット送受信、SSE ストリーミング、セッション履歴、メッセージ評価。FTS5 (`messages_fts`) でセッション横断全文検索 |
| `documents.py` | ファイルアップロード（単発/バッチ）、ドキュメント一覧、タグ確認、再インデックス、ソフトデリート、復元、バージョニング |
| `external.py` | API キー認証付きの同期チャット API、GitHub/Gitea リポジトリ同期エンドポイント |
| `knowledge_bases.py` | KB の CRUD、お気に入り管理、SQLite カスケード削除 + Qdrant ベクトル削除の両方を実行 |
| `master.py` | サイト・ライン・工程マスタの参照（`master_cache` から読み出し） |
| `users.py` | `/users/me` 系の設定・行動プロファイル・メモリ。ユーザー未存在時は自動生成 |
| `__init__.py` | パッケージマーカー |

## For AI Agents

### Working In This Directory
- 各ファイルは `router = APIRouter(prefix="/...", tags=["..."])` を定義し、`app.include_router(router, prefix="/api")` で登録する。最終 URL は `/api/<router_prefix>/...` になる。
- ユーザー識別は `x_user_id: str = Header(..., alias="X-User-Id")`。`users.py` の getter で「未存在なら生成」のロジックを既に持っているので新ルーターからはそれを呼ぶ。
- 外部連携ルーター（`external.py`）のみ `Depends(verify_api_key)` を使う。
- DB セッションは `db: AsyncSession = Depends(get_db)` で受け取る。コミットは `get_db` 内で自動。
- ストリーミングレスポンスは `fastapi.responses.StreamingResponse` + SSE フォーマット (`data: {...}\n\n`)。`api/sse.ts` のフロント実装と一対一で対応するイベント型を維持する。

### Testing Requirements
- 各ルーターは `tests/test_api_<name>.py` を持つ（`knowledge_bases`, `users` は実装済）。新ルーター追加時はテストも追加し、`tests/conftest.py:client` フィクスチャの `include_router` 列にも追記する。

### Common Patterns
- Pydantic モデルはルーター内で定義（小さいため別ファイルに分けない）。
- 削除系は SQLite カスケード（ORM `cascade="all, delete-orphan"`）と Qdrant 側の `delete_by_*` を両方呼ぶ。片方を忘れると孤児ベクトルが残る。

## Dependencies

### Internal
- `app/services/*` — 業務ロジック
- `app/infrastructure/db.py:get_db`
- `app/middleware/api_key.py:verify_api_key`（external のみ）

### External
- `fastapi`

<!-- MANUAL: -->
