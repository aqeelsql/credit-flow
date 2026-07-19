from __future__ import annotations

import json
from typing import Any

import asyncpg


def _json(value: dict[str, Any] | None) -> str:
    return json.dumps(value or {}, default=str)


class AuditRepository:
    def __init__(self, conn: asyncpg.Connection):
        self.conn = conn

    async def insert_event(self, *, event_id: str, routing_key: str, exchange: str | None, account_id: str | None, actor_user_id: str | None, action: str, summary: str | None, payload: dict[str, Any]) -> bool:
        row = await self.conn.fetchrow(
            """
            INSERT INTO audit_log (event_id, routing_key, exchange, account_id, actor_user_id, action, summary, payload, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, now())
            ON CONFLICT (event_id) DO NOTHING
            RETURNING id
            """,
            event_id,
            routing_key,
            exchange,
            account_id,
            actor_user_id,
            action,
            summary,
            _json(payload),
        )
        return row is not None

    async def search(self, *, account_id: str | None, action: str | None, actor_user_id: str | None, q: str | None, limit: int, offset: int) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if account_id:
            params.append(account_id)
            clauses.append(f"account_id = ${len(params)}")
        if action:
            params.append(action)
            clauses.append(f"action = ${len(params)}")
        if actor_user_id:
            params.append(actor_user_id)
            clauses.append(f"actor_user_id = ${len(params)}")
        if q:
            params.append(f"%{q}%")
            clauses.append(f"(routing_key ILIKE ${len(params)} OR action ILIKE ${len(params)} OR summary ILIKE ${len(params)})")
        where_sql = "WHERE " + " AND ".join(clauses) if clauses else ""
        params.extend([limit, offset])
        rows = await self.conn.fetch(
            f"""
            SELECT id::text AS id, event_id, routing_key, exchange, account_id, actor_user_id, action, summary, payload, created_at
            FROM audit_log
            {where_sql}
            ORDER BY created_at DESC
            LIMIT ${len(params) - 1} OFFSET ${len(params)}
            """,
            *params,
        )
        return [dict(row) for row in rows]
