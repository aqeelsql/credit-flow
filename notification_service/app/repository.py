from __future__ import annotations

import json
from typing import Any

import asyncpg


def _json(value: dict[str, Any] | None) -> str:
    return json.dumps(value or {}, default=str)


class NotificationRepository:
    def __init__(self, conn: asyncpg.Connection):
        self.conn = conn

    async def claim_event(self, event_id: str, event_type: str) -> bool:
        row = await self.conn.fetchrow(
            """
            INSERT INTO processed_events (event_id, event_type, processed, created_at)
            VALUES ($1, $2, false, now())
            ON CONFLICT (event_id) DO NOTHING
            RETURNING event_id
            """,
            event_id,
            event_type,
        )
        return row is not None

    async def mark_event_processed(self, event_id: str) -> None:
        await self.conn.execute("UPDATE processed_events SET processed = true, processed_at = now() WHERE event_id = $1", event_id)

    async def mark_event_unprocessed(self, event_id: str) -> None:
        await self.conn.execute("DELETE FROM processed_events WHERE event_id = $1 AND processed = false", event_id)

    async def log_attempt(self, *, event_id: str, event_type: str, notification_type: str, channel: str, recipient: str, subject: str | None, status: str, provider: str = "smtp", provider_message_id: str | None = None, attempt: int = 1, error: str | None = None, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        row = await self.conn.fetchrow(
            """
            INSERT INTO notification_log (event_id, event_type, notification_type, channel, recipient, subject, status, provider, provider_message_id, attempt, error, metadata, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12::jsonb, now())
            RETURNING id::text AS id, event_id, event_type, notification_type, channel, recipient, subject, status, provider, provider_message_id, attempt, error, metadata, created_at
            """,
            event_id,
            event_type,
            notification_type,
            channel,
            recipient,
            subject,
            status,
            provider,
            provider_message_id,
            attempt,
            error[:2000] if error else None,
            _json(metadata),
        )
        return dict(row)

    async def list_logs(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = await self.conn.fetch(
            """
            SELECT id::text AS id, event_id, event_type, notification_type, channel, recipient, subject, status, provider, provider_message_id, attempt, error, metadata, created_at
            FROM notification_log
            ORDER BY created_at DESC
            LIMIT $1
            """,
            limit,
        )
        return [dict(row) for row in rows]
