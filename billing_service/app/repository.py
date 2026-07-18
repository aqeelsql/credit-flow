from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from typing import Any

import asyncpg


def _json(value: dict[str, Any] | None) -> str:
    return json.dumps(value or {}, default=str)


class BillingRepository:
    def __init__(self, conn: asyncpg.Connection):
        self.conn = conn

    async def get_subscription(self, account_id: str) -> dict[str, Any] | None:
        row = await self.conn.fetchrow("SELECT *, id::text AS id FROM subscriptions WHERE account_id = $1", account_id)
        return dict(row) if row else None

    async def upsert_customer(self, account_id: str, stripe_customer_id: str, plan: str = "free", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        row = await self.conn.fetchrow(
            """
            INSERT INTO subscriptions (account_id, stripe_customer_id, plan, status, metadata, created_at, updated_at)
            VALUES ($1, $2, $3, 'active', $4::jsonb, now(), now())
            ON CONFLICT (account_id) DO UPDATE SET stripe_customer_id = EXCLUDED.stripe_customer_id, metadata = subscriptions.metadata || EXCLUDED.metadata, updated_at = now()
            RETURNING *, id::text AS id
            """,
            account_id, stripe_customer_id, plan, _json(metadata),
        )
        return dict(row)

    async def update_subscription_state(self, *, account_id: str, customer_id: str | None, subscription_id: str | None, plan: str | None, status: str, period_end: datetime | None = None, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        row = await self.conn.fetchrow(
            """
            INSERT INTO subscriptions (account_id, stripe_customer_id, stripe_subscription_id, plan, status, current_period_end, metadata, created_at, updated_at)
            VALUES ($1, COALESCE($2, ''), $3, COALESCE($4, 'free'), $5, $6, $7::jsonb, now(), now())
            ON CONFLICT (account_id) DO UPDATE SET stripe_customer_id = COALESCE(NULLIF($2, ''), subscriptions.stripe_customer_id), stripe_subscription_id = COALESCE($3, subscriptions.stripe_subscription_id), plan = COALESCE($4, subscriptions.plan), status = $5, current_period_end = COALESCE($6, subscriptions.current_period_end), metadata = subscriptions.metadata || $7::jsonb, updated_at = now()
            RETURNING *, id::text AS id
            """,
            account_id, customer_id, subscription_id, plan, status, period_end, _json(metadata),
        )
        return dict(row)

    async def record_webhook_event(self, event_id: str, event_type: str, account_id: str | None, payload: dict[str, Any]) -> bool:
        row = await self.conn.fetchrow(
            """
            INSERT INTO subscription_events (stripe_event_id, event_type, account_id, payload, processed, created_at)
            VALUES ($1, $2, $3, $4::jsonb, false, now())
            ON CONFLICT (stripe_event_id) DO NOTHING
            RETURNING id
            """,
            event_id, event_type, account_id, _json(payload),
        )
        return row is not None

    async def mark_webhook_processed(self, event_id: str) -> None:
        await self.conn.execute("UPDATE subscription_events SET processed = true WHERE stripe_event_id = $1", event_id)

    async def upsert_invoice(self, *, account_id: str | None, invoice: dict[str, Any], event_id: str | None, raw_event: dict[str, Any]) -> dict[str, Any]:
        row = await self.conn.fetchrow(
            """
            INSERT INTO invoices (account_id, stripe_invoice_id, stripe_customer_id, stripe_subscription_id, amount_paid, amount_due, currency, status, hosted_invoice_url, invoice_pdf, stripe_event_id, raw_event, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12::jsonb, now(), now())
            ON CONFLICT (stripe_invoice_id) DO UPDATE SET account_id = COALESCE(EXCLUDED.account_id, invoices.account_id), amount_paid = EXCLUDED.amount_paid, amount_due = EXCLUDED.amount_due, status = EXCLUDED.status, hosted_invoice_url = EXCLUDED.hosted_invoice_url, invoice_pdf = EXCLUDED.invoice_pdf, raw_event = EXCLUDED.raw_event, updated_at = now()
            RETURNING id::text AS id, account_id, stripe_invoice_id, stripe_customer_id, stripe_subscription_id,
                amount_paid, amount_due, currency, status, hosted_invoice_url, invoice_pdf, stripe_event_id,
                raw_event, created_at, updated_at
            """,
            account_id,
            str(invoice.get("id")),
            str(invoice.get("customer")) if invoice.get("customer") else None,
            str(invoice.get("subscription")) if invoice.get("subscription") else None,
            int(invoice.get("amount_paid") or 0),
            int(invoice.get("amount_due") or 0),
            str(invoice.get("currency") or "usd"),
            str(invoice.get("status") or "received"),
            invoice.get("hosted_invoice_url"),
            invoice.get("invoice_pdf"),
            event_id,
            _json(raw_event),
        )
        return dict(row)

    async def list_invoices(self, account_id: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = await self.conn.fetch("SELECT id::text AS id, stripe_invoice_id, amount_paid, amount_due, currency, status, hosted_invoice_url, invoice_pdf, created_at FROM invoices WHERE account_id = $1 ORDER BY created_at DESC LIMIT $2", account_id, limit)
        return [dict(row) for row in rows]

    async def create_refund_record(self, account_id: str, invoice_id: str, amount: int, currency: str, reason: str | None) -> dict[str, Any]:
        row = await self.conn.fetchrow("""
            INSERT INTO refunds (account_id, invoice_id, amount, currency, reason, status, created_at, updated_at)
            VALUES ($1, $2::uuid, $3, $4, $5, 'pending', now(), now())
            RETURNING id::text AS id, account_id, invoice_id::text AS invoice_id, stripe_refund_id,
                amount, currency, reason, status, created_at, updated_at
        """, account_id, invoice_id, amount, currency, reason)
        return dict(row)

    async def mark_refund_issued(self, refund_id: str, stripe_refund_id: str | None, status: str = "succeeded") -> dict[str, Any]:
        row = await self.conn.fetchrow("""
            UPDATE refunds SET stripe_refund_id = $2, status = $3, updated_at = now()
            WHERE id = $1::uuid
            RETURNING id::text AS id, account_id, invoice_id::text AS invoice_id, stripe_refund_id,
                amount, currency, reason, status, created_at, updated_at
        """, refund_id, stripe_refund_id, status)
        return dict(row)

    async def get_invoice_by_id(self, invoice_id: str, account_id: str | None = None) -> dict[str, Any] | None:
        if account_id:
            row = await self.conn.fetchrow("""
                SELECT id::text AS id, account_id, stripe_invoice_id, stripe_customer_id, stripe_subscription_id,
                    amount_paid, amount_due, currency, status, hosted_invoice_url, invoice_pdf,
                    stripe_event_id, raw_event, created_at, updated_at
                FROM invoices WHERE id = $1::uuid AND account_id = $2
            """, invoice_id, account_id)
        else:
            row = await self.conn.fetchrow("""
                SELECT id::text AS id, account_id, stripe_invoice_id, stripe_customer_id, stripe_subscription_id,
                    amount_paid, amount_due, currency, status, hosted_invoice_url, invoice_pdf,
                    stripe_event_id, raw_event, created_at, updated_at
                FROM invoices WHERE id = $1::uuid
            """, invoice_id)
        return dict(row) if row else None

    async def add_outbox_event(self, routing_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        row = await self.conn.fetchrow("INSERT INTO outbox_events (routing_key, payload, created_at) VALUES ($1, $2::jsonb, now()) RETURNING id::text AS id, routing_key, payload", routing_key, _json(payload))
        return dict(row)

    async def claim_outbox_batch(self, limit: int) -> list[dict[str, Any]]:
        rows = await self.conn.fetch("SELECT id::text AS id, routing_key, payload FROM outbox_events WHERE published = false ORDER BY created_at ASC LIMIT $1", limit)
        return [dict(row) for row in rows]

    async def mark_outbox_published(self, event_id: str) -> None:
        await self.conn.execute("UPDATE outbox_events SET published = true, published_at = now(), last_error = NULL WHERE id = $1::uuid", event_id)

    async def mark_outbox_failed(self, event_id: str, error: str) -> None:
        await self.conn.execute("UPDATE outbox_events SET publish_attempts = publish_attempts + 1, last_error = $2 WHERE id = $1::uuid", event_id, error[:2000])

    async def mark_payment_failed(self, account_id: str, grace_seconds: int) -> dict[str, Any]:
        grace_ends = datetime.now(UTC) + timedelta(seconds=grace_seconds)
        row = await self.conn.fetchrow("""
            UPDATE subscriptions
            SET status = 'past_due', payment_failed_at = now(), grace_period_ends_at = $2, updated_at = now()
            WHERE account_id = $1
            RETURNING id::text AS id, account_id, stripe_customer_id, stripe_subscription_id,
                plan, status, payment_failed_at, grace_period_ends_at
        """, account_id, grace_ends)
        return dict(row) if row else {}

    async def downgrade_expired_dunning(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = await self.conn.fetch("UPDATE subscriptions SET plan = 'free', status = 'downgraded', updated_at = now() WHERE status = 'past_due' AND grace_period_ends_at <= now() RETURNING id::text AS id, account_id, stripe_customer_id, stripe_subscription_id, plan, status")
        return [dict(row) for row in rows[:limit]]

    async def confirm_marketplace_escrow(self, account_id: str, listing_id: str, payment_intent_id: str | None) -> dict[str, Any]:
        row = await self.conn.fetchrow("INSERT INTO marketplace_escrow (account_id, listing_id, payment_intent_id, status, created_at) VALUES ($1, $2, $3, 'confirmed', now()) ON CONFLICT (account_id, listing_id) DO UPDATE SET payment_intent_id = COALESCE(EXCLUDED.payment_intent_id, marketplace_escrow.payment_intent_id) RETURNING id::text AS id, account_id, listing_id, payment_intent_id, status", account_id, listing_id, payment_intent_id)
        return dict(row)
