"""
RAG Phantom バックエンドアプリケーションのエントリポイント。
FastAPI アプリケーションの設定、ミドルウェア、ルーター登録を行う。
"""

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.infrastructure.config import config
from app.infrastructure.db import close_db, init_db
from app.infrastructure.master_cache import load_master_cache
from app.infrastructure.qdrant_client import init_collections
from app.middleware.csrf import CSRFOriginMiddleware
from app.routers import chat, documents, external, knowledge_bases, master, users
from app.services.cleanup_job import cancel_scheduler_task, create_scheduler_task

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    アプリケーションのライフサイクルイベントハンドラ。
    起動時にデータベースとマスターキャッシュを初期化し、
    終了時にデータベース接続を閉じる。
    """
    # 起動処理
    # SECRET_KEY 検証: production 環境ではデフォルト値での起動を拒否する。
    if (
        config.ENVIRONMENT == "production"
        and config.SECRET_KEY == "dev-secret-key-change-in-production"
    ):
        raise RuntimeError(
            "SECRET_KEY must be changed in production environment. "
            "Set SECRET_KEY env var to a strong random value."
        )
    if config.SECRET_KEY == "dev-secret-key-change-in-production":
        logger.warning(
            "SECRET_KEY がデフォルト値のままです。"
            "production 環境では必ず強力なランダム値に変更してください。"
        )

    await init_db()

    # Qdrant コレクションの自動作成（接続失敗時はアプリ起動を継続する）
    try:
        init_collections()
        logger.info("lifespan: Qdrant collections initialized")
    except Exception as e:
        logger.warning(
            "Qdrant collections initialization skipped (server unreachable?): %s", e
        )

    try:
        await load_master_cache()
    except Exception as e:
        logger.warning("Master cache load skipped: %s", e)

    # 外部 API キー未設定の警告（外部ルーター /api/ext/* を保護できないため）
    if not config.API_KEYS:
        logger.warning(
            "API_KEYS が未設定です。外部 API ルーター (/api/ext/*) は"
            "すべての要求を 403 で拒否します。"
            "本番環境では .env に強力なランダム文字列を設定してください。"
        )

    # ソフトデリート自動パージスケジューラを起動する
    create_scheduler_task()
    logger.info("lifespan: cleanup scheduler task started")

    yield

    # 終了処理
    cancel_scheduler_task()
    await close_db()


def create_app() -> FastAPI:
    """
    FastAPI アプリケーションインスタンスを生成して返す。

    Returns:
        設定済みの FastAPI インスタンス。
    """
    app = FastAPI(
        title="RAG Phantom API",
        version="0.1.0",
        description="RAG Phantom バックエンド API",
        lifespan=lifespan,
    )

    # CORS ミドルウェアの設定（必要なメソッド/ヘッダのみ明示的に許可する）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-User-Id", "X-API-Key"],
    )

    # CSRF 防御ミドルウェア（CORS の後に追加し、状態変更系リクエストの
    # Origin/Referer を allowlist で検証する）
    app.add_middleware(
        CSRFOriginMiddleware,
        allowed_origins=config.ALLOWED_ORIGINS,
    )

    # ルーターの登録（/api プレフィックス付き）
    app.include_router(chat.router, prefix="/api")
    app.include_router(documents.router, prefix="/api")
    app.include_router(users.router, prefix="/api")
    app.include_router(master.router, prefix="/api")
    app.include_router(knowledge_bases.router, prefix="/api")
    app.include_router(external.router, prefix="/api")

    return app


app = create_app()


@app.get("/health", tags=["system"])
async def health_check() -> dict[str, str]:
    """
    ヘルスチェックエンドポイント。
    ロードバランサーやコンテナオーケストレーターから使用される。

    Returns:
        サービスの状態を示す辞書。
    """
    return {"status": "ok"}
