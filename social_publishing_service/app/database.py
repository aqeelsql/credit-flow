from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import re

import asyncpg

from app.config import Settings
from app.errors import SocialPublishingError

_SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def validate_schema(schema: str) -> None:
    if not _SCHEMA_RE.match(schema):
        raise SocialPublishingError("invalid_database_schema", "Database schema name is invalid.", 500)


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
            raise SocialPublishingError("database_unavailable", "PostgreSQL is unavailable or schema bootstrap failed.", 503) from exc

    async def bootstrap(self) -> None:
        schema = self.settings.database_schema
        validate_schema(schema)
        conn = await asyncpg.connect(dsn=self.settings.database_url)
        try:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public")
            await conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
            await conn.execute(f'''
                CREATE TABLE IF NOT EXISTS "{schema}".social_connections (
                    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                    account_id varchar(128) NOT NULL UNIQUE,
                    created_by_user_id varchar(128) NOT NULL,
                    provider varchar(32) NOT NULL DEFAULT 'linkedin',
                    linkedin_sub varchar(255),
                    linkedin_member_urn varchar(255),
                    profile_name varchar(255),
                    email varchar(255),
                    picture text,
                    encrypted_access_token text NOT NULL,
                    encrypted_refresh_token text,
                    scopes text[] NOT NULL DEFAULT ARRAY[]::text[],
                    token_expires_at timestamptz,
                    refresh_token_expires_at timestamptz,
                    status varchar(24) NOT NULL DEFAULT 'connected',
                    connected_at timestamptz NOT NULL DEFAULT now(),
                    refreshed_at timestamptz,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now()
                )
            ''')
            await conn.execute(f'''
                CREATE TABLE IF NOT EXISTS "{schema}".publish_jobs (
                    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                    account_id varchar(128) NOT NULL,
                    scheduled_post_id uuid,
                    content_id uuid NOT NULL,
                    connection_id uuid REFERENCES "{schema}".social_connections(id),
                    status varchar(24) NOT NULL DEFAULT 'queued',
                    attempts integer NOT NULL DEFAULT 0,
                    last_error text,
                    linkedin_post_id text,
                    linkedin_post_url text,
                    payload jsonb NOT NULL DEFAULT '{{}}'::jsonb,
                    published_at timestamptz,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now(),
                    UNIQUE(account_id, scheduled_post_id)
                )
            ''')
            await conn.execute(f'''
                CREATE TABLE IF NOT EXISTS "{schema}".post_media (
                    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                    publish_job_id uuid REFERENCES "{schema}".publish_jobs(id) ON DELETE CASCADE,
                    content_id uuid NOT NULL,
                    source_url text,
                    image_asset_ref text,
                    linkedin_asset_urn text,
                    upload_url text,
                    status varchar(24) NOT NULL DEFAULT 'pending',
                    created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now()
                )
            ''')
            await conn.execute(f'CREATE INDEX IF NOT EXISTS ix_social_connections_account ON "{schema}".social_connections (account_id)')
            await conn.execute(f'CREATE INDEX IF NOT EXISTS ix_publish_jobs_account_status ON "{schema}".publish_jobs (account_id, status)')
            await conn.execute(f'CREATE INDEX IF NOT EXISTS ix_publish_jobs_content ON "{schema}".publish_jobs (content_id)')
        finally:
            await conn.close()

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def pool(self) -> asyncpg.Pool:
        await self.connect()
        if self._pool is None:
            raise SocialPublishingError("database_unavailable", "PostgreSQL is unavailable.", 503)
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
