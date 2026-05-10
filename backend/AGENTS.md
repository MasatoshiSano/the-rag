<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-10 | Updated: 2026-05-10 -->

# backend

## Purpose
FastAPI による RAG Phantom バックエンド。`uvicorn app.main:app` をエントリポイントとし、SQLite (aiosqlite + WAL) でメタデータ・チャット履歴・ユーザー設定を、Qdrant でベクトルを永続化する。Bedrock 経由で Claude Sonnet 4.5 を呼ぶエージェンティック RAG パイプライン、Oracle / DuckDB クエリ、ドキュメント変換 (`pymupdf4llm` / `pptx2md` / `xl2md` / `python-docx`) を一体提供する。

## Key Files
| File | Description |
|------|-------------|
| `Dockerfile` | `python:3.12-slim` ベース、`requirements.txt` をインストールし `uvicorn` で起動 |
| `requirements.txt` | FastAPI 0.115, SQLAlchemy 2.0, qdrant-client, boto3, oracledb, pymupdf4llm, duckdb, pytest 等の固定バージョン |
| `insert_sample_data.py` | 開発用のサンプルナレッジベース・ドキュメント投入スクリプト |
| `.dockerignore` | Docker ビルド時の除外設定 |

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `app/` | FastAPI アプリケーション本体（`app/AGENTS.md`） |
| `data/` | マスタデータ・SQLite DB の永続化ボリューム（`data/AGENTS.md`） |
| `tests/` | pytest テストスイート（`tests/AGENTS.md`） |

## For AI Agents

### Working In This Directory
- 起動順は `lifespan`（`app/main.py`）で制御される: `init_db` → `load_master_cache` → `create_scheduler_task`。マスタロード失敗は warning に降格して継続する。
- 環境変数は `pydantic-settings` 経由で `app/infrastructure/config.py` の `Config` に集約されている。新しい設定値はそこに追加する。
- SQLite は `StaticPool` で接続を 1 本に固定する。並行 WRITE 競合を避けるため別接続を増やさない。
- Alembic は依存にあるが現状未使用。スキーマ変更は `app/models/database.py` を直接編集し、`init_db` 内の `ALTER TABLE` フォールバックでマイグレーション互換を取る。

### Testing Requirements
- `cd backend && pytest`。`tests/conftest.py` が `qdrant_client`・`boto3`・`app.infrastructure.{db,bedrock_client,qdrant_client,master_cache}` をすべて `MagicMock`/`AsyncMock` に差し替えるので、テスト実行に外部接続は不要。
- 新しいルーターを追加したら `tests/conftest.py` の `client` フィクスチャの `include_router` リストにも追加する。
- Bedrock 呼び出しを増やしたら `bedrock_stub` に対応する `AsyncMock` 属性も追加する。

### Common Patterns
- 全ての公開関数・クラスに日本語の docstring。引数説明は `Args:` / 戻り値は `Returns:` / 例外は `Raises:` セクション。
- Bedrock クライアントは `tenacity` の `@retry(stop=stop_after_attempt(config.MAX_RETRY_COUNT), wait=wait_exponential(...))` で指数バックオフリトライ。
- LLM ストリームは `boto3.client("bedrock-runtime").invoke_model_with_response_stream` を `asyncio.to_thread` でラップして `AsyncGenerator[str, None]` を返すパターンに統一。

## Dependencies

### Internal
- `data/master/master-flat-with-place-aliases.md` — `master_cache` が起動時にパースする
- `../uploads/` — マウントされたアップロードディレクトリ

### External
- `fastapi==0.115.0`, `uvicorn[standard]==0.30.0`
- `sqlalchemy[asyncio]==2.0.32`, `aiosqlite==0.20.0`, `alembic==1.13.0`
- `boto3==1.35.0`, `qdrant-client==1.11.0`, `oracledb==2.4.0`
- `pymupdf4llm`, `pptx2md`, `xl2md`, `python-docx`, `beautifulsoup4`, `markdownify`
- `duckdb`, `tenacity`, `python-jose`, `httpx`

<!-- MANUAL: -->
