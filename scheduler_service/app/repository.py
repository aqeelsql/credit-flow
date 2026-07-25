from datetime import datetime, timezone
from typing import Any
import uuid
from zoneinfo import ZoneInfo

import asyncpg

from app.errors import SchedulerError

RETURNING_COLUMNS = """
    id::text AS id, account_id, created_by_user_id, content_id::text AS content_id,
    content_title, publish_at, timezone, recurrence, status, dispatch_attempts,
    last_error, locked_at, dispatched_at, cancelled_at, created_at, updated_at
"""


def as_uuid(value: str | uuid.UUID) -> uuid.UUID:
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except ValueError as exc:
        raise SchedulerError("invalid_uuid", "ID is invalid.", 422) from exc


def with_local_time(row: dict[str, Any]) -> dict[str, Any]:
    try:
        local = row["publish_at"].astimezone(ZoneInfo(row["timezone"]))
        row["publish_at_local"] = local.isoformat()
    except Exception:
        row["publish_at_local"] = row["publish_at"].isoformat()
    return row


class SchedulerRepository:
    def __init__(self, conn: asyncpg.Connection):
        self.conn = conn

    async def create(self, account_id: str, user_id: str, content_id: str, content_title: str, publish_at: datetime, timezone_name: str, recurrence: str) -> dict[str, Any]:
        if publish_at <= datetime.now(timezone.utc):
            raise SchedulerError("publish_time_in_past", "Publish time must be in the future.", 422)
        content_uuid = as_uuid(content_id)
        title = content_title[:255] or "Untitled content"
        row = await self.conn.fetchrow(
            f"""
            UPDATE scheduled_posts
            SET content_title = $3, publish_at = $4, timezone = $5, recurrence = $6,
                status = 'scheduled', cancelled_at = NULL, dispatched_at = NULL, locked_at = NULL,
                last_error = NULL, updated_at = now()
            WHERE id = (
                SELECT id FROM scheduled_posts
                WHERE account_id = $1 AND content_id = $2 AND status = 'scheduled'
                ORDER BY updated_at DESC
                LIMIT 1
            )
            RETURNING {RETURNING_COLUMNS}
            """,
            account_id,
            content_uuid,
            title,
            publish_at,
            timezone_name,
            recurrence,
        )
        if row is None:
            row = await self.conn.fetchrow(
                f"""
                INSERT INTO scheduled_posts (account_id, created_by_user_id, content_id, content_title, publish_at, timezone, recurrence)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING {RETURNING_COLUMNS}
                """,
                account_id,
                user_id,
                content_uuid,
                title,
                publish_at,
                timezone_name,
                recurrence,
            )
        await self._cancel_duplicate_active_schedules(account_id, content_uuid, row["id"])
        return with_local_time(dict(row))

    async def _cancel_duplicate_active_schedules(self, account_id: str, content_id: uuid.UUID, keep_id: uuid.UUID | str) -> None:
        await self.conn.execute(
            """
            UPDATE scheduled_posts
            SET status = 'cancelled', cancelled_at = now(), locked_at = NULL, updated_at = now(),
                last_error = 'Superseded by a newer schedule for this content.'
            WHERE account_id = $1 AND content_id = $2 AND id <> $3 AND status = 'scheduled'
            """,
            account_id,
            content_id,
            as_uuid(keep_id),
        )

    async def list_range(self, account_id: str, start: datetime, end: datetime) -> list[dict[str, Any]]:
        rows = await self.conn.fetch(
            f"""
            SELECT {RETURNING_COLUMNS} FROM scheduled_posts
            WHERE account_id = $1 AND publish_at >= $2 AND publish_at < $3 AND status != 'cancelled'
            ORDER BY publish_at ASC
            """,
            account_id,
            start,
            end,
        )
        return [with_local_time(dict(row)) for row in rows]

    async def get(self, scheduled_post_id: str, account_id: str) -> dict[str, Any] | None:
        row = await self.conn.fetchrow(f"SELECT {RETURNING_COLUMNS} FROM scheduled_posts WHERE id = $1 AND account_id = $2", as_uuid(scheduled_post_id), account_id)
        return with_local_time(dict(row)) if row else None

    async def reschedule(self, scheduled_post_id: str, account_id: str, publish_at: datetime, timezone_name: str, recurrence: str | None = None) -> dict[str, Any]:
        if publish_at <= datetime.now(timezone.utc):
            raise SchedulerError("publish_time_in_past", "Publish time must be in the future.", 422)
        row = await self.conn.fetchrow(
            f"""
            UPDATE scheduled_posts
            SET publish_at = $3, timezone = $4, recurrence = COALESCE($5, recurrence), updated_at = now(), last_error = NULL
            WHERE id = $1 AND account_id = $2 AND status = 'scheduled'
            RETURNING {RETURNING_COLUMNS}
            """,
            as_uuid(scheduled_post_id),
            account_id,
            publish_at,
            timezone_name,
            recurrence,
        )
        if row is None:
            raise SchedulerError("scheduled_post_not_found", "Scheduled post was not found or cannot be rescheduled.", 404)
        await self._cancel_duplicate_active_schedules(account_id, as_uuid(row["content_id"]), row["id"])
        return with_local_time(dict(row))

    async def cancel(self, scheduled_post_id: str, account_id: str) -> dict[str, Any]:
        row = await self.conn.fetchrow(
            f"""
            UPDATE scheduled_posts
            SET status = 'cancelled', cancelled_at = now(), updated_at = now()
            WHERE id = $1 AND account_id = $2 AND status = 'scheduled'
            RETURNING {RETURNING_COLUMNS}
            """,
            as_uuid(scheduled_post_id),
            account_id,
        )
        if row is None:
            raise SchedulerError("scheduled_post_not_found", "Scheduled post was not found or cannot be cancelled.", 404)
        return with_local_time(dict(row))
