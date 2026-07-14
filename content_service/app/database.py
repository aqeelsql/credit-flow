import re
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from app.config import Settings
from app.errors import ContentError

_SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def validate_schema(schema: str) -> None:
    if not _SCHEMA_RE.match(schema):
        raise ContentError("invalid_database_schema", "Database schema name is invalid.", 500)


class Database:
    def __init__(self, settings: Settings):
        self.settings = settings

    def connect(self):
        validate_schema(self.settings.database_schema)
        return psycopg.connect(
            self.settings.database_url,
            row_factory=dict_row,
            autocommit=False,
            options=f"-c search_path={self.settings.database_schema},public",
        )

    def bootstrap(self) -> None:
        schema = self.settings.database_schema
        validate_schema(schema)
        with psycopg.connect(self.settings.database_url, autocommit=True) as conn:
            conn.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public")
            conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS "{schema}".content (
                    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                    account_id varchar(128) NOT NULL,
                    created_by_user_id varchar(128) NOT NULL,
                    title varchar(255) NOT NULL,
                    body text NOT NULL,
                    prompt text,
                    status varchar(24) NOT NULL DEFAULT 'draft',
                    source_generation_job_id uuid,
                    image_url text,
                    image_asset_ref text,
                    metadata jsonb NOT NULL DEFAULT '{{}}'::jsonb,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now(),
                    approved_at timestamptz,
                    published_at timestamptz,
                    deleted_at timestamptz
                )
                """
            )
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS "{schema}".content_versions (
                    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                    content_id uuid NOT NULL REFERENCES "{schema}".content(id) ON DELETE CASCADE,
                    version_number integer NOT NULL,
                    title varchar(255) NOT NULL,
                    body text NOT NULL,
                    prompt text,
                    image_url text,
                    image_asset_ref text,
                    status varchar(24) NOT NULL,
                    created_by_user_id varchar(128) NOT NULL,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    UNIQUE (content_id, version_number)
                )
                """
            )
            conn.execute(
                f"""CREATE INDEX IF NOT EXISTS ix_content_account_status_updated
                ON "{schema}".content (account_id, status, updated_at)"""
            )
            conn.execute(
                f"""CREATE INDEX IF NOT EXISTS ix_content_generation_job
                ON "{schema}".content (source_generation_job_id)"""
            )

    def ping(self) -> bool:
        try:
            with self.connect() as conn:
                conn.execute("SELECT 1")
            return True
        except Exception:
            return False

    @contextmanager
    def transaction(self):
        with self.connect() as conn:
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
