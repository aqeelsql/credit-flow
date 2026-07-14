from enum import Enum

from sqlalchemy import CheckConstraint, Column, DateTime, Index, Integer, MetaData, String, Table, Text, text
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID


class ListingStatus(str, Enum):
    ACTIVE = "active"
    SOLD = "sold"
    CANCELLED = "cancelled"


class LedgerReason(str, Enum):
    PURCHASE = "purchase"
    CONSUMPTION = "consumption"
    MARKETPLACE_SALE = "marketplace_sale"
    MARKETPLACE_PURCHASE = "marketplace_purchase"
    REFUND = "refund"
    ADJUSTMENT = "adjustment"


def build_metadata(schema: str) -> MetaData:
    metadata = MetaData(schema=schema)
    listing_status = PgEnum(*(status.value for status in ListingStatus), name="listing_status", schema=schema)
    ledger_reason = PgEnum(*(reason.value for reason in LedgerReason), name="ledger_reason", schema=schema)

    credits_ledger = Table(
        "credits_ledger",
        metadata,
        Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
        Column("account_id", String(128), nullable=False),
        Column("amount", Integer, nullable=False),
        Column("reason", ledger_reason, nullable=False),
        Column("source_event_id", String(160)),
        Column("related_account_id", String(128)),
        Column("listing_id", UUID(as_uuid=True)),
        Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
        CheckConstraint("amount <> 0", name="ck_credits_ledger_amount_nonzero"),
    )

    marketplace_listings = Table(
        "marketplace_listings",
        metadata,
        Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
        Column("seller_account_id", String(128), nullable=False),
        Column("credits", Integer, nullable=False),
        Column("price_cents", Integer, nullable=False),
        Column("currency", String(8), nullable=False, server_default="usd"),
        Column("status", listing_status, nullable=False, server_default=ListingStatus.ACTIVE.value),
        Column("buyer_account_id", String(128)),
        Column("created_by_user_id", String(128)),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
        Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
        Column("sold_at", DateTime(timezone=True)),
        CheckConstraint("credits > 0", name="ck_marketplace_listings_credits_positive"),
        CheckConstraint("price_cents > 0", name="ck_marketplace_listings_price_positive"),
    )

    processed_events = Table(
        "processed_events",
        metadata,
        Column("event_id", String(160), primary_key=True),
        Column("routing_key", String(160), nullable=False),
        Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
        Column("processed_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    )

    Index("ix_credits_ledger_account_created", credits_ledger.c.account_id, credits_ledger.c.created_at)
    Index("ix_credits_ledger_source_event", credits_ledger.c.source_event_id)
    Index("ix_marketplace_listings_status_created", marketplace_listings.c.status, marketplace_listings.c.created_at)
    Index("ix_marketplace_listings_seller_status", marketplace_listings.c.seller_account_id, marketplace_listings.c.status)
    Index("ix_processed_events_routing", processed_events.c.routing_key, processed_events.c.processed_at)
    return metadata
