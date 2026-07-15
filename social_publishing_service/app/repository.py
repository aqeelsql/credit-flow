from datetime import datetime, timedelta, timezone
import json
from typing import Any

from asyncpg import UniqueViolationError


CONNECTION_COLUMNS = """
    id::text AS id, account_id, created_by_user_id, provider, linkedin_sub, linkedin_member_urn,
    profile_name, email, picture, encrypted_access_token, encrypted_refresh_token, scopes,
    token_expires_at, refresh_token_expires_at, status, connected_at, refreshed_at, created_at, updated_at
"""

JOB_COLUMNS = """
    id::text AS id, account_id, scheduled_post_id::text AS scheduled_post_id, content_id::text AS content_id,
    connection_id::text AS connection_id, status, attempts, last_error, linkedin_post_id,
    linkedin_post_url, payload, published_at, created_at, updated_at
"""


class SocialRepository:
    def __init__(self, conn):
        self.conn = conn

    async def upsert_connection(self, *, account_id: str, user_id: str, profile: dict[str, Any], encrypted_access_token: str, encrypted_refresh_token: str | None, scopes: list[str], expires_in: int | None, refresh_token_expires_in: int | None = None) -> dict:
        now = datetime.now(timezone.utc)
        token_expires_at = now + timedelta(seconds=expires_in) if expires_in else None
        refresh_expires_at = now + timedelta(seconds=refresh_token_expires_in) if refresh_token_expires_in else None
        sub = profile.get("sub")
        member_urn = f"urn:li:person:{sub}" if sub else None
        return await self.conn.fetchrow(
            f"""
            INSERT INTO social_connections (account_id, created_by_user_id, linkedin_sub, linkedin_member_urn, profile_name, email, picture, encrypted_access_token, encrypted_refresh_token, scopes, token_expires_at, refresh_token_expires_at, status, connected_at, updated_at)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,'connected',now(),now())
            ON CONFLICT (account_id) DO UPDATE SET
                created_by_user_id = EXCLUDED.created_by_user_id,
                linkedin_sub = EXCLUDED.linkedin_sub,
                linkedin_member_urn = EXCLUDED.linkedin_member_urn,
                profile_name = EXCLUDED.profile_name,
                email = EXCLUDED.email,
                picture = EXCLUDED.picture,
                encrypted_access_token = EXCLUDED.encrypted_access_token,
                encrypted_refresh_token = COALESCE(EXCLUDED.encrypted_refresh_token, social_connections.encrypted_refresh_token),
                scopes = EXCLUDED.scopes,
                token_expires_at = EXCLUDED.token_expires_at,
                refresh_token_expires_at = COALESCE(EXCLUDED.refresh_token_expires_at, social_connections.refresh_token_expires_at),
                status = 'connected',
                connected_at = now(),
                updated_at = now()
            RETURNING {CONNECTION_COLUMNS}
            """,
            account_id,
            user_id,
            sub,
            member_urn,
            profile.get("name"),
            profile.get("email"),
            profile.get("picture"),
            encrypted_access_token,
            encrypted_refresh_token,
            scopes,
            token_expires_at,
            refresh_expires_at,
        )

    async def get_connection(self, account_id: str) -> dict | None:
        return await self.conn.fetchrow(f"SELECT {CONNECTION_COLUMNS} FROM social_connections WHERE account_id = $1 AND status = 'connected'", account_id)

    async def disconnect(self, account_id: str) -> dict | None:
        return await self.conn.fetchrow(f"UPDATE social_connections SET status = 'disconnected', updated_at = now() WHERE account_id = $1 RETURNING {CONNECTION_COLUMNS}", account_id)

    async def connections_needing_refresh(self, leeway_seconds: int, limit: int = 50) -> list[dict]:
        return await self.conn.fetch(
            f"""
            SELECT {CONNECTION_COLUMNS}
            FROM social_connections
            WHERE status = 'connected'
              AND encrypted_refresh_token IS NOT NULL
              AND (token_expires_at IS NULL OR token_expires_at <= now() + make_interval(secs => $1::int))
            ORDER BY token_expires_at NULLS FIRST
            LIMIT $2
            """,
            leeway_seconds,
            limit,
        )

    async def update_connection_tokens(self, connection_id: str, encrypted_access_token: str, encrypted_refresh_token: str | None, expires_in: int | None) -> dict:
        token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in) if expires_in else None
        return await self.conn.fetchrow(
            f"""
            UPDATE social_connections
            SET encrypted_access_token = $2,
                encrypted_refresh_token = COALESCE($3, encrypted_refresh_token),
                token_expires_at = $4,
                refreshed_at = now(),
                updated_at = now()
            WHERE id = $1
            RETURNING {CONNECTION_COLUMNS}
            """,
            connection_id,
            encrypted_access_token,
            encrypted_refresh_token,
            token_expires_at,
        )

    async def create_or_get_job(self, *, account_id: str, scheduled_post_id: str | None, content_id: str, payload: dict) -> dict:
        try:
            return await self.conn.fetchrow(
                f"""
                INSERT INTO publish_jobs (account_id, scheduled_post_id, content_id, payload)
                VALUES ($1, $2::uuid, $3::uuid, $4::jsonb)
                RETURNING {JOB_COLUMNS}
                """,
                account_id,
                scheduled_post_id,
                content_id,
                json.dumps(payload, default=str),
            )
        except UniqueViolationError:
            return await self.conn.fetchrow(f"SELECT {JOB_COLUMNS} FROM publish_jobs WHERE account_id = $1 AND scheduled_post_id = $2::uuid", account_id, scheduled_post_id)

    async def mark_job_publishing(self, job_id: str, connection_id: str) -> dict:
        return await self.conn.fetchrow(f"UPDATE publish_jobs SET status = 'publishing', connection_id = $2, attempts = attempts + 1, updated_at = now() WHERE id = $1 RETURNING {JOB_COLUMNS}", job_id, connection_id)

    async def mark_job_published(self, job_id: str, linkedin_post_id: str, linkedin_post_url: str) -> dict:
        return await self.conn.fetchrow(f"UPDATE publish_jobs SET status = 'published', linkedin_post_id = $2, linkedin_post_url = $3, published_at = now(), updated_at = now() WHERE id = $1 RETURNING {JOB_COLUMNS}", job_id, linkedin_post_id, linkedin_post_url)

    async def mark_job_failed(self, job_id: str, reason: str) -> dict:
        return await self.conn.fetchrow(f"UPDATE publish_jobs SET status = 'failed', last_error = $2, updated_at = now() WHERE id = $1 RETURNING {JOB_COLUMNS}", job_id, reason)

    async def list_jobs(self, account_id: str, limit: int = 50) -> list[dict]:
        return await self.conn.fetch(f"SELECT {JOB_COLUMNS} FROM publish_jobs WHERE account_id = $1 ORDER BY updated_at DESC LIMIT $2", account_id, limit)

    async def create_media(self, *, job_id: str, content_id: str, source_url: str | None, image_asset_ref: str | None) -> dict:
        return await self.conn.fetchrow(
            """
            INSERT INTO post_media (publish_job_id, content_id, source_url, image_asset_ref)
            VALUES ($1, $2::uuid, $3, $4)
            RETURNING id::text AS id, publish_job_id::text AS publish_job_id, content_id::text AS content_id, source_url, image_asset_ref, linkedin_asset_urn, upload_url, status, created_at, updated_at
            """,
            job_id,
            content_id,
            source_url,
            image_asset_ref,
        )

    async def mark_media_uploaded(self, media_id: str, asset_urn: str, upload_url: str) -> dict:
        return await self.conn.fetchrow(
            """
            UPDATE post_media SET linkedin_asset_urn = $2, upload_url = $3, status = 'uploaded', updated_at = now()
            WHERE id = $1
            RETURNING id::text AS id, publish_job_id::text AS publish_job_id, content_id::text AS content_id, source_url, image_asset_ref, linkedin_asset_urn, upload_url, status, created_at, updated_at
            """,
            media_id,
            asset_urn,
            upload_url,
        )
