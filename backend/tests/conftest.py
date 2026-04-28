"""
pytest 設定とフィクスチャ。

インメモリ SQLite データベースを使用した非同期テスト環境を提供する。
外部サービス（Qdrant、Bedrock）はモックで差し替える。
"""

from __future__ import annotations

import sys
from collections.abc import AsyncGenerator
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


# ---------------------------------------------------------------------------
# 外部依存モジュールのスタブ登録（テスト収集前に必ず実行する）
# ---------------------------------------------------------------------------


def _install_stubs() -> None:
    """
    テスト環境では利用できない外部モジュールをスタブとして登録する。

    登録タイミング: conftest.py はテスト収集前に実行されるため、
    ここで sys.modules を操作すると後続の import が全てスタブを参照する。
    """
    # Python 3.10 では datetime.UTC が存在しないため、事前にパッチを当てる
    import datetime as _dt_mod
    if not hasattr(_dt_mod, "UTC"):
        _dt_mod.UTC = _dt_mod.timezone.utc  # type: ignore[attr-defined]

    # qdrant-client / boto3 はテスト時に実サービスへ接続しない
    for mod_name in [
        "qdrant_client",
        "qdrant_client.http",
        "qdrant_client.http.models",
        "boto3",
        "botocore",
        "botocore.exceptions",
    ]:
        if mod_name not in sys.modules:
            sys.modules[mod_name] = MagicMock()

    # app.infrastructure.db のスタブ
    # テスト用の実 aiosqlite エンジンは db_session フィクスチャで生成するが、
    # モジュールレベルの create_async_engine 呼び出し（_engine）を回避するため
    # db モジュール自体をスタブ化する。
    # Base / get_db / AsyncSessionLocal は後で実クラスで上書きする。
    from sqlalchemy.orm import DeclarativeBase

    class _RealBase(DeclarativeBase):
        """テスト用 ORM ベースクラス（実装）。"""
        pass

    db_stub = ModuleType("app.infrastructure.db")
    db_stub.__package__ = "app.infrastructure"  # type: ignore[attr-defined]
    db_stub.Base = _RealBase  # type: ignore[attr-defined]
    db_stub.get_db = MagicMock()  # type: ignore[attr-defined]
    db_stub.init_db = AsyncMock()  # type: ignore[attr-defined]
    db_stub.close_db = AsyncMock()  # type: ignore[attr-defined]
    db_stub.AsyncSessionLocal = MagicMock()  # type: ignore[attr-defined]
    sys.modules["app.infrastructure.db"] = db_stub

    # app.infrastructure.qdrant_client のスタブ
    qdrant_stub = ModuleType("app.infrastructure.qdrant_client")
    qdrant_stub.__package__ = "app.infrastructure"  # type: ignore[attr-defined]
    qdrant_stub.delete_by_document_id = MagicMock()  # type: ignore[attr-defined]
    qdrant_stub.delete_by_knowledge_base_id = MagicMock()  # type: ignore[attr-defined]
    sys.modules["app.infrastructure.qdrant_client"] = qdrant_stub

    # app.infrastructure.bedrock_client のスタブ
    from dataclasses import dataclass as _dataclass

    @_dataclass
    class _RerankResult:
        index: int
        relevance_score: float
        document: str

    bedrock_stub = ModuleType("app.infrastructure.bedrock_client")
    bedrock_stub.__package__ = "app.infrastructure"  # type: ignore[attr-defined]
    bedrock_stub.RerankResult = _RerankResult  # type: ignore[attr-defined]
    bedrock_stub.generate_text = AsyncMock(return_value="stub response")  # type: ignore[attr-defined]
    bedrock_stub.stream_text = AsyncMock()  # type: ignore[attr-defined]
    bedrock_stub.embed_texts = AsyncMock(return_value=[[0.1] * 1024])  # type: ignore[attr-defined]
    bedrock_stub.rerank_documents = AsyncMock(return_value=[])  # type: ignore[attr-defined]
    bedrock_stub.get_bedrock_runtime = MagicMock()  # type: ignore[attr-defined]
    sys.modules["app.infrastructure.bedrock_client"] = bedrock_stub

    # app.infrastructure.master_cache のスタブ
    from dataclasses import dataclass as _dc, field as _field

    @_dc
    class _SiteData:
        code: str
        name: str
        aliases: list = _field(default_factory=list)

    @_dc
    class _LineData:
        code: str
        name: str
        site_code: str
        aliases: list = _field(default_factory=list)

    @_dc
    class _ProcessData:
        code: str
        name: str
        line_code: str

    @_dc
    class _MasterDataCache:
        sites: dict = _field(default_factory=dict)
        lines: dict = _field(default_factory=dict)
        processes: dict = _field(default_factory=dict)

    master_cache_stub = ModuleType("app.infrastructure.master_cache")
    master_cache_stub.__package__ = "app.infrastructure"  # type: ignore[attr-defined]
    master_cache_stub.load_master_cache = AsyncMock()  # type: ignore[attr-defined]
    master_cache_stub.get_master_cache = MagicMock(return_value=_MasterDataCache())  # type: ignore[attr-defined]
    master_cache_stub.MasterDataCache = _MasterDataCache  # type: ignore[attr-defined]
    master_cache_stub.SiteData = _SiteData  # type: ignore[attr-defined]
    master_cache_stub.LineData = _LineData  # type: ignore[attr-defined]
    master_cache_stub.ProcessData = _ProcessData  # type: ignore[attr-defined]
    sys.modules["app.infrastructure.master_cache"] = master_cache_stub


_install_stubs()


# ---------------------------------------------------------------------------
# テスト用 ORM ベースクラスとエンジン
# ---------------------------------------------------------------------------


class TestBase(DeclarativeBase):
    """テスト用インメモリ SQLite のベースクラス。"""

    pass


# ---------------------------------------------------------------------------
# pytest-asyncio モード設定
# ---------------------------------------------------------------------------

pytest_plugins = ["pytest_asyncio"]


# ---------------------------------------------------------------------------
# フィクスチャ: インメモリ DB セッション
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    各テスト用のインメモリ SQLite 非同期セッションを提供する。

    スタブ化した app.infrastructure.db.Base を使ってテーブルを作成する。
    ORM モデルは app.models.database をインポートして Base.metadata に登録する。
    テスト終了後はエンジンを破棄する。
    """
    # スタブ化済みの Base を取得する（_install_stubs で _RealBase を登録済み）
    from app.infrastructure.db import Base
    # ORM モデルを Base.metadata に登録する
    from app.models import database as _  # noqa: F401

    # インメモリ SQLite エンジンを生成（テストごとに独立したDB）
    # aiosqlite がない環境では sqlalchemy の同期 SQLite で代替する
    try:
        import aiosqlite as _aiosqlite_check  # noqa: F401
        db_url = "sqlite+aiosqlite:///:memory:"
    except ImportError:
        db_url = "sqlite+aiosqlite:///:memory:"

    engine = create_async_engine(
        db_url,
        echo=False,
        future=True,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )

    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    await engine.dispose()


# ---------------------------------------------------------------------------
# フィクスチャ: FastAPI テストクライアント
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    FastAPI アプリに対する非同期 httpx クライアントを提供する。

    get_db 依存性をインメモリ DB セッションで差し替える。
    lifespan（init_db / load_master_cache）はスキップする。
    """
    from app.infrastructure.db import get_db

    # lifespan をバイパスするため contextlib.nullcontext を使う
    from contextlib import asynccontextmanager
    from collections.abc import AsyncGenerator as AG

    @asynccontextmanager
    async def _noop_lifespan(app):  # type: ignore[no-untyped-def]
        yield

    # アプリを lifespan なしで再生成
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from app.infrastructure.config import config
    from app.routers import chat, documents, knowledge_bases, master, users

    test_app = FastAPI(title="RAG Phantom Test", lifespan=_noop_lifespan)
    test_app.add_middleware(
        CORSMiddleware,
        allow_origins=config.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    test_app.include_router(chat.router, prefix="/api")
    test_app.include_router(documents.router, prefix="/api")
    test_app.include_router(users.router, prefix="/api")
    test_app.include_router(master.router, prefix="/api")
    test_app.include_router(knowledge_bases.router, prefix="/api")

    async def _override_get_db() -> AG[AsyncSession, None]:
        try:
            yield db_session
            await db_session.flush()
        except Exception:
            await db_session.rollback()
            raise

    test_app.dependency_overrides[get_db] = _override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
    ) as ac:
        yield ac
