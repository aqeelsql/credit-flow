from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import json
from typing import Any

import asyncpg


def current_period() -> str:
    return datetime.now(UTC).strftime("%Y-%m")


def event_id_from_generation(payload: dict[str, Any]) -> str:
    explicit = payload.get("event_id") or payload.get("id")
    if explicit:
        return str(explicit)
    job_id = payload.get("job_id")
    if job_id:
        return f"ai.generation_completed:{job_id}"
    request_id = payload.get("request_id")
    if request_id:
        return f"ai.generation_completed:{request_id}"
    return f"ai.generation_completed:{payload.get('account_id', 'unknown')}:{payload.get('completed_at') or datetime.now(UTC).isoformat()}"


def _json(value: dict[str, Any] | None) -> str:
    return json.dumps(value or {}, default=str)


class UsageRepository:
    def __init__(self, conn: asyncpg.Connection):
        self.conn = conn

    async def record_processed_event(self, event_id: str, routing_key: str, metadata: dict[str, Any] | None = None) -> bool:
        row = await self.conn.fetchrow(
            """
            INSERT INTO processed_events (event_id, routing_key, metadata, processed_at)
            VALUES ($1, $2, $3::jsonb, now())
            ON CONFLICT (event_id) DO NOTHING
            RETURNING event_id
            """,
            event_id, routing_key, _json(metadata),
        )
        return row is not None

    async def quota_for_account(self, account_id: str, default_quota: int) -> dict[str, Any]:
        row = await self.conn.fetchrow("SELECT account_id, monthly_token_quota, enabled, metadata, updated_at FROM account_quotas WHERE account_id = $1", account_id)
        if row is None:
            return {"account_id": account_id, "monthly_token_quota": default_quota, "enabled": True, "metadata": {}, "updated_at": datetime.now(UTC)}
        return dict(row)

    async def upsert_quota(self, account_id: str, monthly_token_quota: int, enabled: bool, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        row = await self.conn.fetchrow(
            """
            INSERT INTO account_quotas (account_id, monthly_token_quota, enabled, metadata, created_at, updated_at)
            VALUES ($1, $2, $3, $4::jsonb, now(), now())
            ON CONFLICT (account_id) DO UPDATE SET monthly_token_quota = EXCLUDED.monthly_token_quota, enabled = EXCLUDED.enabled, metadata = EXCLUDED.metadata, updated_at = now()
            RETURNING account_id, monthly_token_quota, enabled, metadata, updated_at
            """,
            account_id, monthly_token_quota, enabled, _json(metadata),
        )
        return dict(row)

    async def append_usage_from_generation(self, event_id: str, payload: dict[str, Any], currency: str) -> dict[str, Any]:
        prompt_tokens = int(payload.get("prompt_tokens") or 0)
        completion_tokens = int(payload.get("completion_tokens") or 0)
        total_tokens = int(payload.get("total_tokens") or (prompt_tokens + completion_tokens))
        cost = Decimal(str(payload.get("cost") or "0"))
        row = await self.conn.fetchrow(
            """
            INSERT INTO usage_ledger (event_id, generation_job_id, request_id, account_id, user_id, operation, model, prompt_tokens, completion_tokens, total_tokens, cost, currency, metadata, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13::jsonb, now())
            ON CONFLICT (event_id) DO NOTHING
            RETURNING id::text AS id, event_id, generation_job_id, request_id, account_id, user_id, operation, model, prompt_tokens, completion_tokens, total_tokens, cost, currency, metadata, created_at
            """,
            event_id,
            str(payload.get("job_id")) if payload.get("job_id") is not None else None,
            str(payload.get("request_id")) if payload.get("request_id") is not None else None,
            str(payload.get("account_id")),
            str(payload.get("user_id")) if payload.get("user_id") is not None else None,
            str(payload.get("operation") or "text_generation"),
            str(payload.get("model") or "unknown"),
            prompt_tokens, completion_tokens, total_tokens, cost, currency,
            _json({"source": "ai.generation_completed", "payload": payload}),
        )
        return dict(row) if row is not None else {}

    async def used_tokens(self, account_id: str, period: str | None = None) -> int:
        query = "SELECT COALESCE(SUM(total_tokens), 0)::bigint FROM usage_ledger WHERE account_id = $1"
        args: list[Any] = [account_id]
        if period:
            query += " AND created_at >= $2::date AND created_at < ($2::date + interval '1 month')"
            args.append(f"{period}-01")
        value = await self.conn.fetchval(query, *args)
        return int(value or 0)

    async def summary(self, account_id: str | None = None, period: str | None = None) -> dict[str, Any]:
        where, args = [], []
        if account_id:
            args.append(account_id); where.append(f"account_id = ${len(args)}")
        if period:
            args.append(f"{period}-01"); where.append(f"created_at >= ${len(args)}::date AND created_at < (${len(args)}::date + interval '1 month')")
        where_sql = "WHERE " + " AND ".join(where) if where else ""
        rows = await self.conn.fetch(
            f"""
            SELECT model, COALESCE(SUM(prompt_tokens), 0)::bigint AS prompt_tokens, COALESCE(SUM(completion_tokens), 0)::bigint AS completion_tokens, COALESCE(SUM(total_tokens), 0)::bigint AS total_tokens, COALESCE(SUM(cost), 0)::numeric AS total_cost, COUNT(*)::bigint AS generations
            FROM usage_ledger {where_sql}
            GROUP BY model ORDER BY total_tokens DESC, model ASC
            """,
            *args,
        )
        return {"used_tokens": sum(int(r["total_tokens"] or 0) for r in rows), "total_cost": sum((r["total_cost"] or Decimal("0")) for r in rows), "models": [dict(r) for r in rows]}

    async def record_threshold_alert(self, account_id: str, period: str, threshold: int, usage_tokens: int, quota_tokens: int, source_event_id: str) -> bool:
        row = await self.conn.fetchrow(
            """
            INSERT INTO threshold_alerts (account_id, period, threshold, usage_tokens, quota_tokens, source_event_id, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, now())
            ON CONFLICT (account_id, period, threshold) DO NOTHING
            RETURNING id
            """,
            account_id, period, threshold, usage_tokens, quota_tokens, source_event_id,
        )
        return row is not None

