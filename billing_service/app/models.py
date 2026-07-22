from sqlalchemy import BigInteger, Boolean, CheckConstraint, Column, DateTime, Index, Integer, MetaData, String, Table, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID


def build_metadata(schema: str) -> MetaData:
    metadata = MetaData(schema=schema)

    subscriptions = Table(
        "subscriptions",
        metadata,
        Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
        Column("account_id", String(128), nullable=False, unique=True),
        Column("stripe_customer_id", String(128), nullable=False),
        Column("stripe_subscription_id", String(128)),
        Column("plan", String(40), nullable=False, server_default="free"),
        Column("status", String(40), nullable=False, server_default="active"),
        Column("current_period_end", DateTime(timezone=True)),
        Column("payment_failed_at", DateTime(timezone=True)),
        Column("grace_period_ends_at", DateTime(timezone=True)),
        Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
        Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    )

    invoices = Table(
        "invoices",
        metadata,
        Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
        Column("account_id", String(128)),
        Column("stripe_invoice_id", String(128), unique=True),
        Column("stripe_customer_id", String(128)),
        Column("stripe_subscription_id", String(128)),
        Column("amount_paid", BigInteger, nullable=False, server_default="0"),
        Column("amount_due", BigInteger, nullable=False, server_default="0"),
        Column("currency", String(8), nullable=False, server_default="usd"),
        Column("status", String(40), nullable=False, server_default="received"),
        Column("hosted_invoice_url", Text),
        Column("invoice_pdf", Text),
        Column("stripe_event_id", String(160)),
        Column("raw_event", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
        Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    )

    subscription_events = Table(
        "subscription_events",
        metadata,
        Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
        Column("stripe_event_id", String(160), nullable=False, unique=True),
        Column("event_type", String(120), nullable=False),
        Column("account_id", String(128)),
        Column("payload", JSONB, nullable=False),
        Column("processed", Boolean, nullable=False, server_default=text("false")),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    )

    refunds = Table(
        "refunds",
        metadata,
        Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
        Column("account_id", String(128), nullable=False),
        Column("invoice_id", UUID(as_uuid=True)),
        Column("stripe_refund_id", String(128), unique=True),
        Column("amount", BigInteger, nullable=False),
        Column("currency", String(8), nullable=False, server_default="usd"),
        Column("status", String(40), nullable=False, server_default="pending"),
        Column("reason", Text),
        Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
        Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
        CheckConstraint("amount > 0", name="ck_refunds_amount_positive"),
    )

    outbox_events = Table(
        "outbox_events",
        metadata,
        Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
        Column("routing_key", String(160), nullable=False),
        Column("payload", JSONB, nullable=False),
        Column("published", Boolean, nullable=False, server_default=text("false")),
        Column("publish_attempts", Integer, nullable=False, server_default="0"),
        Column("last_error", Text),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
        Column("published_at", DateTime(timezone=True)),
    )

    marketplace_escrow = Table(
        "marketplace_escrow",
        metadata,
        Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
        Column("account_id", String(128), nullable=False),
        Column("listing_id", String(128), nullable=False),
        Column("payment_intent_id", String(160)),
        Column("status", String(40), nullable=False, server_default="confirmed"),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
        UniqueConstraint("account_id", "listing_id", name="uq_marketplace_escrow_account_listing"),
    )

    credit_packages = Table(
        "credit_packages",
        metadata,
        Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
        Column("key", String(80), nullable=False, unique=True),
        Column("credits", Integer, nullable=False),
        Column("price_cents", Integer, nullable=False),
        Column("currency", String(8), nullable=False, server_default="usd"),
        Column("active", Boolean, nullable=False, server_default=text("true")),
        Column("created_by_user_id", String(128)),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
        Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
        CheckConstraint("credits > 0", name="ck_credit_packages_credits_positive"),
        CheckConstraint("price_cents > 0", name="ck_credit_packages_price_positive"),
    )

    Index("ix_invoices_account_created", invoices.c.account_id, invoices.c.created_at)
    Index("ix_outbox_unpublished", outbox_events.c.published, outbox_events.c.created_at)
    Index("ix_subscription_events_type_created", subscription_events.c.event_type, subscription_events.c.created_at)
    Index("ix_credit_packages_active_created", credit_packages.c.active, credit_packages.c.created_at)
    return metadata

