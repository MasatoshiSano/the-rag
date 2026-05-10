<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-10 | Updated: 2026-05-10 -->

# infrastructure

## Purpose
外部 I/O アダプタ層。AWS Bedrock・Qdrant・SQLite・マスタ MD ファイルへの接続をシングルトン的に提供し、上位の `services/` / `routers/` から外部リソースの詳細を隠蔽する。

## Key Files
| File | Description |
|------|-------------|
| `config.py` | `pydantic-settings` ベースのアプリ全体設定（Bedrock / Oracle / Qdrant / SQLite / セキュリティ / RAG 閾値 / 外部 API キー等）。シングルトン `config` をエクスポート |
| `db.py` | SQLAlchemy 非同期エンジン（aiosqlite + StaticPool）、`Base`、`get_db` 依存関数、WAL モード設定、FTS5 仮想テーブル `messages_fts` の作成、起動時マイグレーション |
| `bedrock_client.py` | Claude のテキスト生成（同期/ストリーム/Vision/Tool use）と Cohere Embed/Rerank。`tenacity` で指数バックオフリトライ |
| `qdrant_client.py` | `documents`（dense+sparse）と `master_data`（dense のみ）コレクション管理、ハイブリッド検索、ペイロードインデックス、カスケード削除 |
| `master_cache.py` | `master-flat-with-place-aliases.md` を解析し、`SiteData` / `LineData` / `ProcessData` をメモリキャッシュ。SQLite (`MasterSite/Line/Process`) への UPSERT も提供 |
| `__init__.py` | パッケージマーカー |

## For AI Agents

### Working In This Directory
- すべて**シングルトン**: `_engine`（db）、`_bedrock_runtime`、`_client`（qdrant）、`_cache`（master）。`get_*` 関数経由で取得し、テストでは `conftest.py` がモジュールごと `MagicMock` で差し替える。
- `db.py:init_db` は (1) `Base.metadata.create_all` (2) FTS5 仮想テーブル作成 (3) 既存 DB 互換のための `ALTER TABLE` を順に実行する。新カラム追加時はここに `ALTER TABLE ... ADD COLUMN` を追記する。
- Bedrock のリトライは全ての API 呼び出しに付ける。`@retry(stop=stop_after_attempt(config.MAX_RETRY_COUNT), wait=wait_exponential(multiplier=1, min=1, max=8), retry=retry_if_exception_type(Exception), reraise=True)` を踏襲。
- Qdrant の `documents` コレクションは **named vectors**（`dense` / `sparse`）構造、`master_data` は **unnamed vector**。混同するとクエリで `BadRequest` になる。

### Testing Requirements
- このレイヤの単体テストは原則書かない。サービス層からの利用を介して動作確認する。
- `conftest.py:_install_stubs` で `app.infrastructure.{db, bedrock_client, qdrant_client, master_cache}` 全てをスタブ化済み。新しい関数を追加したら対応するスタブも追記する。

### Common Patterns
- `dataclass` で API 結果型を定義（`SearchResult`, `RerankResult`, `ToolUseBlock`, `TextBlock`, `ModelResponse`, `Site/Line/ProcessData`）。
- Bedrock 呼び出しは `asyncio.to_thread(client.invoke_model, ...)` でブロッキング boto3 を非同期化。

## Dependencies

### Internal
- `app/services/text_normalizer.py` — `master_cache.py` が NFKC 正規化に使用

### External
- `boto3`, `qdrant-client`, `sqlalchemy[asyncio]`, `aiosqlite`, `pydantic-settings`, `tenacity`

<!-- MANUAL: -->
