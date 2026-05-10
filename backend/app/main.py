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
from app.routers import chat, documents, external, knowledge_bases, master, users
from app.services.cleanup_job import cancel_scheduler_task, create_scheduler_task

logger = logging.getLogger(__name__)

# 起動時バリデーションで拒否する既知の弱い（公知の）デフォルト値
_WEAK_SECRET_KEY = "dev-secret-key-change-in-production"  # noqa: S105
_WEAK_API_KEY = "the-rag-default-key"  # noqa: S105


def validate_security_settings() -> None:
    """
    起動時にセキュリティ関連の設定を検証する。

    SECRET_KEY が未設定または既知の弱い値の場合、および API_KEYS に
    既知の弱いデフォルトキーが含まれる場合は RuntimeError を送出して起動を中止する。
    API_KEYS が空の場合は外部 API エンドポイントを無効化する旨を警告ログに出力する。

    Raises:
        RuntimeError: セキュリティ設定が安全でない場合。
    """
    if not config.SECRET_KEY or config.SECRET_KEY == _WEAK_SECRET_KEY:
        raise RuntimeError(
            "SECRET_KEY が未設定または既知の弱い値です。環境変数 SECRET_KEY に"
            "ランダムな値を設定してください（.env.example を参照）。"
        )

    if _WEAK_API_KEY in config.API_KEYS:
        raise RuntimeError(
            f"API_KEYS に既知の弱いデフォルトキー {_WEAK_API_KEY!r} が含まれています。"
            "環境変数 API_KEYS をランダムな値に変更してください。"
        )

    if not config.API_KEYS:
        logger.warning(
            "API_KEYS が未設定のため、外部 API エンドポイント (/api/external/*) は"
            "全リクエストを拒否します。利用する場合は環境変数 API_KEYS を設定してください。"
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    アプリケーションのライフサイクルイベントハンドラ。
    起動時にデータベースとマスターキャッシュを初期化し、
    終了時にデータベース接続を閉じる。
    """
    # 起動処理
    validate_security_settings()
    await init_db()
    try:
        await load_master_cache()
    except Exception as e:
        logger.warning("Master cache load skipped: %s", e)

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

    # CORS ミドルウェアの設定
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
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
