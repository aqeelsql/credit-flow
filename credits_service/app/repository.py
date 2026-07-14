import json
import uuid
from typing import Any

import asyncpg

from app.errors import CreditsError
from app.models import LedgerReason, ListingStatus


def _as_dict(row: asyncpg.Record | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def _uuid(value: str | uuid.UUID) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def _uuid_or_none(value: str | uuid.UUID | None) -> uuid.UUID | None:
    return None if value is None else _uuid(value)


def _metadata(value: dict[str, Any] | None) -> str:
    return json.dumps(value or {})


class CreditsRepository:
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
            event_id,
            routing_key,
            _metadata(metadata),
        )
        return row is not None

    async def balance(self, account_id: str) -> int:
        value = await self.conn.fetchval(
            """
            SELECT COALESCE(SUM(amount), 0)::bigint
            FROM credits_ledger
            WHERE account_id = $1
            """,
            account_id,
        )
        return int(value or 0)

    async def append_ledger_entry(
        self,
        account_id: str,
        amount: int,
        reason: LedgerReason,
        source_event_id: str | None = None,
        related_account_id: str | None = None,
        listing_id: str | uuid.UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        row = await self.conn.fetchrow(
            """
            INSERT INTO credits_ledger (
                id, account_id, amount, reason, source_event_id, related_account_id, listing_id, metadata, created_at
            )
            VALUES (gen_random_uuid(), $1, $2, $3::ledger_reason, $4, $5, $6, $7::jsonb, now())
            RETURNING
                id::text AS id,
                account_id,
                amount,
                reason::text AS reason,
                source_event_id,
                related_account_id,
                listing_id::text AS listing_id,
                metadata,
                created_at
            """,
            account_id,
            amount,
            reason.value,
            source_event_id,
            related_account_id,
            _uuid_or_none(listing_id),
            _metadata(metadata),
        )
        if row is None:
            raise CreditsError("ledger_append_failed", "Unable to append credits ledger entry.", 500)
        return dict(row)

    async def list_transactions(self, account_id: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = await self.conn.fetch(
            """
            SELECT
                id::text AS id,
                account_id,
                amount,
                reason::text AS reason,
                source_event_id,
                related_account_id,
                listing_id::text AS listing_id,
                metadata,
                created_at
            FROM credits_ledger
            WHERE account_id = $1
            ORDER BY created_at DESC, id DESC
            LIMIT $2
            """,
            account_id,
            limit,
        )
        return [dict(row) for row in rows]

    async def create_listing(
        self,
        seller_account_id: str,
        credits: int,
        price_cents: int,
        currency: str,
        created_by_user_id: str,
    ) -> dict[str, Any]:
        balance = await self.balance(seller_account_id)
        if balance < credits:
            raise CreditsError(
                "insufficient_credits",
                "Account does not have enough credits to list this amount.",
                409,
                {"balance": balance, "requested": credits},
            )
        row = await self.conn.fetchrow(
            """
            INSERT INTO marketplace_listings (
                id, seller_account_id, credits, price_cents, currency, status, created_by_user_id, created_at, updated_at
            )
            VALUES (gen_random_uuid(), $1, $2, $3, $4, $5::listing_status, $6, now(), now())
            RETURNING
                id::text AS id,
                seller_account_id,
                credits,
                price_cents,
                currency,
                status::text AS status,
                buyer_account_id,
                created_by_user_id,
                created_at,
                updated_at,
                sold_at
            """,
            seller_account_id,
            credits,
            price_cents,
            currency,
            ListingStatus.ACTIVE.value,
            created_by_user_id,
        )
        if row is None:
            raise CreditsError("listing_create_failed", "Unable to create marketplace listing.", 500)
        return dict(row)

    async def list_active_listings(self, account_id: str | None = None, include_own: bool = True) -> list[dict[str, Any]]:
        if account_id and not include_own:
            rows = await self.conn.fetch(
                """
                SELECT
                    id::text AS id,
                    seller_account_id,
                    credits,
                    price_cents,
                    currency,
                    status::text AS status,
                    buyer_account_id,
                    created_by_user_id,
                    created_at,
                    updated_at,
                    sold_at
                FROM marketplace_listings
                WHERE status = $1::listing_status AND seller_account_id <> $2
                ORDER BY created_at DESC
                """,
                ListingStatus.ACTIVE.value,
                account_id,
            )
        else:
            rows = await self.conn.fetch(
                """
                SELECT
                    id::text AS id,
                    seller_account_id,
                    credits,
                    price_cents,
                    currency,
                    status::text AS status,
                    buyer_account_id,
                    created_by_user_id,
                    created_at,
                    updated_at,
                    sold_at
                FROM marketplace_listings
                WHERE status = $1::listing_status
                ORDER BY created_at DESC
                """,
                ListingStatus.ACTIVE.value,
            )
        return [dict(row) for row in rows]

    async def list_account_listings(self, account_id: str) -> list[dict[str, Any]]:
        rows = await self.conn.fetch(
            """
            SELECT
                id::text AS id,
                seller_account_id,
                credits,
                price_cents,
                currency,
                status::text AS status,
                buyer_account_id,
                created_by_user_id,
                created_at,
                updated_at,
                sold_at
            FROM marketplace_listings
            WHERE seller_account_id = $1
            ORDER BY created_at DESC
            """,
            account_id,
        )
        return [dict(row) for row in rows]

    async def get_listing(self, listing_id: str | uuid.UUID) -> dict[str, Any] | None:
        row = await self.conn.fetchrow(
            """
            SELECT
                id::text AS id,
                seller_account_id,
                credits,
                price_cents,
                currency,
                status::text AS status,
                buyer_account_id,
                created_by_user_id,
                created_at,
                updated_at,
                sold_at
            FROM marketplace_listings
            WHERE id = $1
            """,
            _uuid(listing_id),
        )
        return _as_dict(row)

    async def cancel_listing(self, listing_id: str, account_id: str) -> dict[str, Any]:
        row = await self.conn.fetchrow(
            """
            UPDATE marketplace_listings
            SET status = $1::listing_status, updated_at = now()
            WHERE id = $2 AND seller_account_id = $3 AND status = $4::listing_status
            RETURNING
                id::text AS id,
                seller_account_id,
                credits,
                price_cents,
                currency,
                status::text AS status,
                buyer_account_id,
                created_by_user_id,
                created_at,
                updated_at,
                sold_at
            """,
            ListingStatus.CANCELLED.value,
            _uuid(listing_id),
            account_id,
            ListingStatus.ACTIVE.value,
        )
        if row is None:
            raise CreditsError("listing_not_cancelled", "Listing was not found, already closed, or not owned by this account.", 404)
        return dict(row)

    async def buy_listing(self, listing_id: str, buyer_account_id: str, event_id: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        processed = await self.record_processed_event(event_id, "marketplace.purchase", metadata)
        if not processed:
            existing = await self.get_listing(listing_id)
            if existing is None:
                raise CreditsError("listing_not_found", "Marketplace listing was not found.", 404)
            return existing

        listing = await self.conn.fetchrow(
            """
            SELECT
                id::text AS id,
                seller_account_id,
                credits,
                price_cents,
                currency,
                status::text AS status,
                buyer_account_id,
                created_by_user_id,
                created_at,
                updated_at,
                sold_at
            FROM marketplace_listings
            WHERE id = $1 AND status = $2::listing_status
            FOR UPDATE
            """,
            _uuid(listing_id),
            ListingStatus.ACTIVE.value,
        )
        if listing is None:
            raise CreditsError("listing_unavailable", "Marketplace listing is unavailable.", 409)
        if listing["seller_account_id"] == buyer_account_id:
            raise CreditsError("cannot_buy_own_listing", "An account cannot buy its own listing.", 409)

        seller_balance = await self.balance(listing["seller_account_id"])
        if seller_balance < listing["credits"]:
            raise CreditsError(
                "seller_balance_insufficient",
                "Seller no longer has enough credits to complete this sale.",
                409,
                {"seller_balance": seller_balance, "credits": listing["credits"]},
            )

        await self.append_ledger_entry(
            listing["seller_account_id"],
            -int(listing["credits"]),
            LedgerReason.MARKETPLACE_SALE,
            event_id,
            buyer_account_id,
            listing["id"],
            metadata,
        )
        await self.append_ledger_entry(
            buyer_account_id,
            int(listing["credits"]),
            LedgerReason.MARKETPLACE_PURCHASE,
            event_id,
            listing["seller_account_id"],
            listing["id"],
            metadata,
        )

        sold = await self.conn.fetchrow(
            """
            UPDATE marketplace_listings
            SET status = $1::listing_status, buyer_account_id = $2, sold_at = now(), updated_at = now()
            WHERE id = $3
            RETURNING
                id::text AS id,
                seller_account_id,
                credits,
                price_cents,
                currency,
                status::text AS status,
                buyer_account_id,
                created_by_user_id,
                created_at,
                updated_at,
                sold_at
            """,
            ListingStatus.SOLD.value,
            buyer_account_id,
            _uuid(listing_id),
        )
        if sold is None:
            raise CreditsError("listing_purchase_failed", "Unable to complete marketplace purchase.", 500)
        return dict(sold)

    async def consume_credits(self, account_id: str, amount: int, event_id: str, metadata: dict[str, Any] | None = None) -> tuple[dict[str, Any] | None, bool]:
        processed = await self.record_processed_event(event_id, "credits.consume", metadata)
        if not processed:
            return None, False
        balance = await self.balance(account_id)
        if balance < amount:
            raise CreditsError("insufficient_credits", "Account does not have enough credits.", 409, {"balance": balance, "requested": amount})
        entry = await self.append_ledger_entry(account_id, -amount, LedgerReason.CONSUMPTION, event_id, None, None, metadata)
        return entry, True

    async def credit_account(
        self,
        account_id: str,
        amount: int,
        event_id: str,
        reason: LedgerReason = LedgerReason.PURCHASE,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, bool]:
        processed = await self.record_processed_event(event_id, f"credits.{reason.value}", metadata)
        if not processed:
            return None, False
        entry = await self.append_ledger_entry(account_id, amount, reason, event_id, None, None, metadata)
        return entry, True

    async def debit_account(
        self,
        account_id: str,
        amount: int,
        event_id: str,
        reason: LedgerReason = LedgerReason.REFUND,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, bool]:
        processed = await self.record_processed_event(event_id, f"credits.{reason.value}", metadata)
        if not processed:
            return None, False
        entry = await self.append_ledger_entry(account_id, -amount, reason, event_id, None, None, metadata)
        return entry, True
