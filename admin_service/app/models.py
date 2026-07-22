from sqlalchemy import Column, DateTime, Index, MetaData, String, Table, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID


def build_metadata(schema: str) -> MetaData:
    metadata = MetaData(schema=schema)

    audit_log = Table(
        "audit_log",
        metadata,
        Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
        Column("event_id", String(180), nullable=False),
        Column("routing_key", String(180), nullable=False),
        Column("exchange", String(180)),
        Column("account_id", String(128)),
        Column("actor_user_id", String(128)),
        Column("action", String(180), nullable=False),
        Column("summary", Text),
        Column("payload", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
        UniqueConstraint("event_id", name="uq_audit_log_event_id"),
    )

    Index("ix_audit_log_account_created", audit_log.c.account_id, audit_log.c.created_at)
    Index("ix_audit_log_action_created", audit_log.c.action, audit_log.c.created_at)
    Index("ix_audit_log_actor_created", audit_log.c.actor_user_id, audit_log.c.created_at)
    return metadata
