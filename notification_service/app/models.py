from sqlalchemy import Boolean, Column, DateTime, Index, Integer, MetaData, String, Table, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID


def build_metadata(schema: str) -> MetaData:
    metadata = MetaData(schema=schema)

    notification_log = Table(
        "notification_log",
        metadata,
        Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
        Column("event_id", String(160), nullable=False),
        Column("event_type", String(160), nullable=False),
        Column("notification_type", String(120), nullable=False),
        Column("channel", String(40), nullable=False, server_default="email"),
        Column("recipient", String(320), nullable=False),
        Column("subject", Text),
        Column("status", String(40), nullable=False),
        Column("provider", String(80), nullable=False, server_default="resend"),
        Column("provider_message_id", String(160)),
        Column("attempt", Integer, nullable=False, server_default="1"),
        Column("error", Text),
        Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    )

    processed_events = Table(
        "processed_events",
        metadata,
        Column("event_id", String(160), primary_key=True),
        Column("event_type", String(160), nullable=False),
        Column("processed", Boolean, nullable=False, server_default=text("false")),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
        Column("processed_at", DateTime(timezone=True)),
    )

    Index("ix_notification_log_event", notification_log.c.event_id, notification_log.c.event_type)
    Index("ix_notification_log_recipient_created", notification_log.c.recipient, notification_log.c.created_at)
    Index("ix_notification_log_status_created", notification_log.c.status, notification_log.c.created_at)
    return metadata
