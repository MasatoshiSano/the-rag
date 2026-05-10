"""
SQLAlchemy 非同期データベース接続モジュール。
SQLite + aiosqlite を使用し、WAL モードを有効化する。
"""

import logging
from collections.abc import AsyncGenerator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import StaticPool

from app.infrastructure.config import config

logger = logging.getLogger(__name__)

# 非同期エンジンの作成（SQLite + aiosqlite）
# StaticPool: 接続を1つに固定して並行 WRITE 競合を排除する
_engine = create_async_engine(
    f"sqlite+aiosqlite:///{config.SQLITE_DB_PATH}",
    echo=False,
    future=True,
    connect_args={"check_same_thread": False, "timeout": 30},
    poolclass=StaticPool,
)


@event.listens_for(_engine.sync_engine, "connect")
def _set_wal_mode(dbapi_connection, connection_record) -> None:  # type: ignore[no-untyped-def]
    """
    SQLite 接続時に WAL（Write-Ahead Logging）モードを有効化する。
    同時読み書き性能を向上させるために使用する。
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()


# 非同期セッションファクトリ
AsyncSessionLocal = async_sessionmaker(
    bind=_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    """全 ORM モデルの基底クラス。"""

    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI 依存性注入用の非同期データベースセッションジェネレータ。

    Yields:
        AsyncSession: 非同期データベースセッション。
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


_FTS5_VIRTUAL_TABLE_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts
USING fts5(content, content='messages', content_rowid='rowid');
"""

_FTS5_TRIGGER_INSERT_SQL = """
CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
  INSERT INTO messages_fts(rowid, content) VALUES (new.rowid, new.content);
END;
"""

_FTS5_TRIGGER_DELETE_SQL = """
CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
  INSERT INTO messages_fts(messages_fts, rowid, content) VALUES('delete', old.rowid, old.content);
END;
"""

_FTS5_TRIGGER_UPDATE_SQL = """
CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
  INSERT INTO messages_fts(messages_fts, rowid, content) VALUES('delete', old.rowid, old.content);
  INSERT INTO messages_fts(rowid, content) VALUES (new.rowid, new.content);
END;
"""


async def create_fts5_tables(conn: AsyncConnection) -> None:
    """
    messages テーブルに対する FTS5 仮想テーブルとトリガーを作成する。

    FTS5（Full-Text Search 5）を使用してメッセージの全文検索を高速化する。
    トリガーにより messages テーブルとの自動同期が保たれる。

    Args:
        conn: 実行に使用する非同期データベース接続。
    """
    await conn.execute(text(_FTS5_VIRTUAL_TABLE_SQL))
    await conn.execute(text(_FTS5_TRIGGER_INSERT_SQL))
    await conn.execute(text(_FTS5_TRIGGER_DELETE_SQL))
    await conn.execute(text(_FTS5_TRIGGER_UPDATE_SQL))


async def init_db() -> None:
    """
    アプリケーション起動時にデータベーステーブルを初期化する。

    実行順序:
      1. ORM モデルをインポートして Base のメタデータに登録する。
      2. Base.metadata.create_all で全 ORM テーブルを作成する。
      3. create_fts5_tables で FTS5 仮想テーブルとトリガーを作成する。
    """
    # ORM モデルを登録するためにインポートする
    from app.models import database as _  # noqa: F401

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await create_fts5_tables(conn)

        # 簡易マイグレーション: 既存 DB に不足カラムを追加する。
        # カラムが既に存在する場合は SQLite が "duplicate column" エラーを返すため握りつぶす
        # （その他のエラーも起動を止めないが、原因調査用に debug ログへ記録する）。
        for stmt in [
            "ALTER TABLE users ADD COLUMN search_mode TEXT NOT NULL DEFAULT 'normal'",
            "ALTER TABLE users ADD COLUMN agentic_max_iterations INTEGER NOT NULL DEFAULT 10",
            "ALTER TABLE folder_sources ADD COLUMN source_type TEXT NOT NULL DEFAULT 'document'",
        ]:
            try:
                await conn.execute(text(stmt))
            except Exception as exc:
                logger.debug("ALTER TABLE をスキップしました: %s (%s)", stmt, exc)


async def close_db() -> None:
    """アプリケーション終了時にデータベース接続プールを閉じる。"""
    await _engine.dispose()
