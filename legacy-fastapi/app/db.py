import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import DateTime, Text, event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import TypeDecorator

from app.security import decrypt_bytes, encrypt_bytes


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator):
    """Timezone-aware UTC datetimes on every backend (SQLite drops tzinfo)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Naive datetimes are not allowed; use app.db.utcnow()")
        return value.astimezone(UTC)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class EncryptedString(TypeDecorator):
    """Personal data encrypted with the app's Fernet key before it reaches the database."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return encrypt_bytes(value.encode()).decode()

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return decrypt_bytes(value.encode()).decode()


class EncryptedJSON(TypeDecorator):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return encrypt_bytes(json.dumps(value).encode()).decode()

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return json.loads(decrypt_bytes(value.encode()))


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _enable_sqlite_foreign_keys(dbapi_connection, connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def init_db(database_url: str) -> AsyncEngine:
    global _engine, _sessionmaker
    url = make_url(database_url)
    connect_args = {}
    if url.get_backend_name() == "sqlite":
        connect_args["timeout"] = 30
        if url.database and url.database != ":memory:":
            Path(url.database).parent.mkdir(parents=True, exist_ok=True)
    _engine = create_async_engine(database_url, connect_args=connect_args)
    if url.get_backend_name() == "sqlite":
        # SQLite ignores foreign keys unless asked; enforce them like Postgres does.
        event.listen(_engine.sync_engine, "connect", _enable_sqlite_foreign_keys)
    _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def session_factory() -> async_sessionmaker[AsyncSession]:
    if _sessionmaker is None:
        raise RuntimeError("Database is not initialised; call init_db() at startup")
    return _sessionmaker


async def dispose_db() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_factory()() as session:
        yield session
