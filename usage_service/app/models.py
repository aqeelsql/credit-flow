from sqlalchemy import BigInteger, Boolean, CheckConstraint, Column, DateTime, Index, Integer, MetaData, Numeric, String, Table, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID


def build_metadata(schema: str) -> MetaData:
    metadata = MetaData(schema=schema)

    usage_ledger = Table(
        "usage_ledger",
        metadata,
        Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
        Column("event_id", String(180), nullable=False, unique=True),
        Column("generation_job_id", String(128)),
        Column("request_id", String(160)),
        Column("account_id", String(128), nullable=False),
        Column("user_id", String(128)),
        Column("operation", String(64), nullable=False, server_default="text_generation"),
        Column("model", String(255), nullable=False),
        Column("prompt_tokens", BigInteger, nullable=False, server_default="0"),
        Column("completion_tokens", BigInteger, nullable=False, server_default="0"),
        Column("total_tokens", BigInteger, nullable=False, server_default="0"),
        Column("cost", Numeric(18, 8), nullable=False, server_default="0"),
        Column("currency", String(8), nullable=False, server_default="usd"),
        Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
        CheckConstraint("prompt_tokens >= 0", name="ck_usage_prompt_tokens_nonnegative"),
        CheckConstraint("completion_tokens >= 0", name="ck_usage_completion_tokens_nonnegative"),
        CheckConstraint("total_tokens >= 0", name="ck_usage_total_tokens_nonnegative"),
        CheckConstraint("cost >= 0", name="ck_usage_cost_nonnegative"),
    )

    processed_events = Table(
        "processed_events",
        metadata,
        Column("event_id", String(180), primary_key=True),
        Column("routing_key", String(180), nullable=False),
        Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
        Column("processed_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    )

    account_quotas = Table(
        "account_quotas",
        metadata,
        Column("account_id", String(128), primary_key=True),
        Column("monthly_token_quota", BigInteger, nullable=False),
        Column("enabled", Boolean, nullable=False, server_default=text("true")),
        Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
        Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
        CheckConstraint("monthly_token_quota >= 0", name="ck_account_quotas_nonnegative"),
    )

    threshold_alerts = Table(
        "threshold_alerts",
        metadata,
        Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
        Column("account_id", String(128), nullable=False),
        Column("period", String(7), nullable=False),
        Column("threshold", Integer, nullable=False),
        Column("usage_tokens", BigInteger, nullable=False),
        Column("quota_tokens", BigInteger, nullable=False),
        Column("source_event_id", String(180)),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
        UniqueConstraint("account_id", "period", "threshold", name="uq_threshold_alert_account_period_threshold"),
    )

    Index("ix_usage_ledger_account_created", usage_ledger.c.account_id, usage_ledger.c.created_at)
    Index("ix_usage_ledger_model_created", usage_ledger.c.model, usage_ledger.c.created_at)
    Index("ix_usage_ledger_request", usage_ledger.c.request_id)
    Index("ix_processed_events_routing", processed_events.c.routing_key, processed_events.c.processed_at)
    return metadata

