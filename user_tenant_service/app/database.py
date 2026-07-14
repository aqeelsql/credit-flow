from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import re

import asyncpg
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import Settings
from app.errors import AccountError
from app.models import build_metadata

_SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_schema(schema: str) -> None:
    if not _SCHEMA_RE.match(schema):
        raise AccountError("invalid_database_schema", "Database schema name is invalid.", 500)


def _search_path(schema: str) -> str:
    _validate_schema(schema)
    return f"{schema},public"


def _sqlalchemy_url(database_url: str) -> str:
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return database_url


class Database:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        if self._pool is not None:
            return
        try:
            await self._bootstrap_schema()
            self._pool = await asyncpg.create_pool(
                dsn=self.settings.database_url,
                min_size=1,
                max_size=10,
                command_timeout=30,
                server_settings={"search_path": _search_path(self.settings.database_schema)},
            )
        except Exception as exc:
            raise AccountError("database_unavailable", "PostgreSQL is unavailable or schema bootstrap failed.", 503) from exc

    async def _bootstrap_schema(self) -> None:
        schema = self.settings.database_schema
        _validate_schema(schema)
        engine = create_async_engine(_sqlalchemy_url(self.settings.database_url), pool_pre_ping=True)
        metadata = build_metadata(schema)
        try:
            async with engine.begin() as conn:
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public"))
                await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
                await conn.run_sync(metadata.create_all)
        finally:
            await engine.dispose()

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def pool(self) -> asyncpg.Pool:
        await self.connect()
        if self._pool is None:
            raise AccountError("database_unavailable", "PostgreSQL is unavailable.", 503)
        return self._pool

    async def ping(self) -> bool:
        try:
            pool = await self.pool()
            async with pool.acquire() as conn:
                await conn.execute("SELECT 1")
            return True
        except Exception:
            return False

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[asyncpg.Connection]:
        pool = await self.pool()
        async with pool.acquire() as conn:
            yield conn

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[asyncpg.Connection]:
        pool = await self.pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                yield conn
