<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-10 | Updated: 2026-05-10 -->

# app

## Purpose
RAG Phantom の FastAPI アプリケーション本体。`main.py` がアプリ生成と lifespan、CORS、ルーター登録を行い、`infrastructure/` 層が外部 SaaS（Bedrock / Qdrant / Oracle / SQLite）への接続をまとめ、`services/` 層が RAG パイプライン・ドキュメント変換・タグ付け等のドメインロジックを担う。

## Key Files
| File | Description |
|------|-------------|
| `main.py` | FastAPI アプリ生成、lifespan（DB 初期化・マスタキャッシュ・クリーンアップスケジューラ）、CORS、`/health`、`/api` 配下ルーター登録 |
| `__init__.py` | パッケージマーカー（中身は空） |

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `infrastructure/` | 外部 I/O アダプタ層（`infrastructure/AGENTS.md`） |
| `middleware/` | FastAPI 依存関数として実装される認証ミドルウェア（`middleware/AGENTS.md`） |
| `models/` | SQLAlchemy ORM モデル（`models/AGENTS.md`） |
| `routers/` | HTTP エンドポイント定義（`routers/AGENTS.md`） |
| `services/` | ドメインロジック・RAG パイプライン（`services/AGENTS.md`） |

## For AI Agents

### Working In This Directory
- 新しい API は `routers/` にモジュールを追加し、`main.py:create_app` の `app.include_router(prefix="/api")` 列に登録する。
- 起動時に必須でない初期化（マスタキャッシュなど）は try/except で warning に降格して継続する方針（`main.py:lifespan` 参照）。
- 共通設定値は `infrastructure/config.py` の `Config` クラスにしか書かない。サービスは `from app.infrastructure.config import config` でアクセスする。

### Testing Requirements
- ルーター単位のテストは `tests/test_api_*.py` パターンで `client` フィクスチャを使う。
- サービス層は DB セッションを直接受け取る純粋関数として書き、`db_session` フィクスチャでテストする。

### Common Patterns
- レイヤ依存方向は `routers → services → infrastructure`。逆向き import は禁止。
- 全関数に型ヒント。`Mapped[T]` / `mapped_column` の SQLAlchemy 2.0 スタイル。
- `from __future__ import annotations` を多用し、循環 import を避ける。

## Dependencies

### Internal
- すべての子ディレクトリ

### External
- `fastapi`, `pydantic-settings`, `sqlalchemy`

<!-- MANUAL: -->
