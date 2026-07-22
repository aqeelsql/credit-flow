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
        items: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            payload = item.get("payload")
            if isinstance(payload, str):
                try:
                    decoded = json.loads(payload)
                    item["payload"] = decoded if isinstance(decoded, dict) else {"value": decoded}
                except json.JSONDecodeError:
                    item["payload"] = {"raw": payload}
            elif not isinstance(payload, dict):
                item["payload"] = {}
            items.append(item)
        return items


class PlatformReadRepository:
    def __init__(self, conn: asyncpg.Connection, *, user_tenant_schema: str, billing_schema: str):
        self.conn = conn
        self.user_tenant_schema = _schema_name(user_tenant_schema)
        self.billing_schema = _schema_name(billing_schema)

    async def list_accounts(self, *, q: str | None = None, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        params: list[Any] = []
        clauses: list[str] = []
        if q and q.strip():
            params.append(f"%{q.strip()}%")
            clauses.append(f"(a.id::text ILIKE ${len(params)} OR a.name ILIKE ${len(params)} OR owner.email ILIKE ${len(params)} OR owner.name ILIKE ${len(params)})")
        where_sql = "WHERE " + " AND ".join(clauses) if clauses else ""
        params.extend([limit, offset])
        s = self.user_tenant_schema
        rows = await self.conn.fetch(
            f"""
            SELECT
                a.id::text AS id,
                a.name,
                a.type::text AS type,
                a.plan,
                a.credits,
                COALESCE(active_members.team_size, 0)::int AS team_size,
                COALESCE(owner.name, split_part(owner.email, '@', 1)) AS owner_name,
                owner.email AS owner_email,
                a.created_at::text AS created_at,
                a.updated_at::text AS updated_at
            FROM "{s}".accounts a
            LEFT JOIN LATERAL (
                SELECT count(*) AS team_size
                FROM "{s}".account_members tm
                WHERE tm.account_id = a.id AND tm.status::text = 'active'
            ) active_members ON true
            LEFT JOIN LATERAL (
                SELECT name, email
                FROM "{s}".account_members om
                WHERE om.account_id = a.id
                  AND om.role::text = 'Owner'
                  AND om.status::text = 'active'
                ORDER BY om.created_at ASC
                LIMIT 1
            ) owner ON true
            {where_sql}
            ORDER BY a.created_at DESC
            LIMIT ${len(params) - 1} OFFSET ${len(params)}
            """,
            *params,
        )
        return [dict(row) for row in rows]

    async def credit_package_inventory(self) -> dict[str, Any]:
        s = self.billing_schema
        row = await self.conn.fetchrow(
            f"""
            WITH package_totals AS (
                SELECT
                    COALESCE(SUM(credits), 0)::bigint AS total_credits_generated,
                    COUNT(*)::int AS package_count,
                    COALESCE(SUM(CASE WHEN active THEN credits ELSE 0 END), 0)::bigint AS active_package_credits,
                    COUNT(*) FILTER (WHERE active)::int AS active_package_count
                FROM "{s}".credit_packages
            ), purchase_totals AS (
                SELECT
                    COALESCE(SUM(COALESCE(NULLIF(payload->>'credits_delta', ''), NULLIF(payload->>'credits', ''), '0')::bigint), 0)::bigint AS total_credits_sold,
                    COALESCE(SUM(COALESCE(NULLIF(payload->>'amount_paid', ''), '0')::bigint), 0)::bigint AS total_money_generated_cents,
                    COUNT(*)::int AS purchase_count,
                    COALESCE(mode() WITHIN GROUP (ORDER BY COALESCE(payload->>'currency', 'usd')), 'usd') AS currency
                FROM "{s}".outbox_events
                WHERE routing_key = 'invoice.paid'
                  AND payload->>'purpose' = 'credit_purchase'
            )
            SELECT
                package_totals.total_credits_generated,
                package_totals.package_count,
                package_totals.active_package_credits,
                package_totals.active_package_count,
                purchase_totals.total_credits_sold,
                purchase_totals.total_money_generated_cents,
                purchase_totals.purchase_count,
                purchase_totals.currency,
                GREATEST(package_totals.total_credits_generated - purchase_totals.total_credits_sold, 0)::bigint AS credits_left
            FROM package_totals, purchase_totals
            """
        )
        return dict(row) if row else {
            "total_credits_generated": 0,
            "package_count": 0,
            "active_package_credits": 0,
            "active_package_count": 0,
            "total_credits_sold": 0,
            "total_money_generated_cents": 0,
            "purchase_count": 0,
            "currency": "usd",
            "credits_left": 0,
        }
