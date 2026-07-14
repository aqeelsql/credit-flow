from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import re

import asyncpg

from app.config import Settings
from app.errors import SchedulerError

_SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def validate_schema(schema: str) -> None:
    if not _SCHEMA_RE.match(schema):
        raise SchedulerError("invalid_database_schema", "Database schema name is invalid.", 500)


def search_path(schema: str) -> str:
    validate_schema(schema)
    return f"{schema},public"


class Database:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        if self._pool is not None:
            return
        try:
            await self.bootstrap()
            self._pool = await asyncpg.create_pool(dsn=self.settings.database_url, min_size=1, max_size=10, command_timeout=30, server_settings={"search_path": search_path(self.settings.database_schema)})
        except Exception as exc:
            raise SchedulerError("database_unavailable", "PostgreSQL is unavailable or schema bootstrap failed.", 503) from exc

    async def bootstrap(self) -> None:
        schema = self.settings.database_schema
        validate_schema(schema)
        conn = await asyncpg.connect(dsn=self.settings.database_url)
        try:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public")
            await conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS "{schema}".scheduled_posts (
                    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                    account_id varchar(128) NOT NULL,
                    created_by_user_id varchar(128) NOT NULL,
                    content_id uuid NOT NULL,
                    content_title varchar(255) NOT NULL,
                    publish_at timestamptz NOT NULL,
                    timezone varchar(128) NOT NULL DEFAULT 'UTC',
                    recurrence varchar(24) NOT NULL DEFAULT 'none',
                    status varchar(24) NOT NULL DEFAULT 'scheduled',
                    dispatch_attempts integer NOT NULL DEFAULT 0,
                    last_error text,
                    locked_at timestamptz,
                    dispatched_at timestamptz,
                    cancelled_at timestamptz,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now()
                )
            """)
            await conn.execute(f'CREATE INDEX IF NOT EXISTS ix_scheduled_posts_account_publish ON "{schema}".scheduled_posts (account_id, publish_at)')
            await conn.execute(f'CREATE INDEX IF NOT EXISTS ix_scheduled_posts_due ON "{schema}".scheduled_posts (status, publish_at)')
            await conn.execute(f'CREATE INDEX IF NOT EXISTS ix_scheduled_posts_content ON "{schema}".scheduled_posts (account_id, content_id)')
        finally:
            await conn.close()

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def pool(self) -> asyncpg.Pool:
        await self.connect()
        if self._pool is None:
            raise SchedulerError("database_unavailable", "PostgreSQL is unavailable.", 503)
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
