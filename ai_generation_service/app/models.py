from enum import Enum

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, MetaData, Numeric, String, Table, Text, text
from sqlalchemy.dialects.postgresql import UUID


class GenerationStatus(str, Enum):
    QUEUED = "queued"
    STREAMING = "streaming"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ImageGenerationStatus(str, Enum):
    QUEUED = "queued"
    COMPLETED = "completed"
    FAILED = "failed"


def build_metadata(schema: str) -> MetaData:
    metadata = MetaData(schema=schema)
    generation_jobs = Table(
        "generation_jobs",
        metadata,
        Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
        Column("account_id", String(128), nullable=False),
        Column("user_id", String(128), nullable=False),
        Column("request_id", String(128)),
        Column("channel", String(255), nullable=False, unique=True),
        Column("model", String(255), nullable=False),
        Column("prompt", Text, nullable=False),
        Column("response_text", Text, nullable=False, server_default=text("''")),
        Column("status", String(24), nullable=False, server_default=text("'queued'")),
        Column("prompt_tokens", Integer),
        Column("completion_tokens", Integer),
        Column("total_tokens", Integer),
        Column("cost", Numeric(18, 8)),
        Column("error_reason", Text),
        Column("cancellation_requested", Boolean, nullable=False, server_default=text("false")),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
        Column("started_at", DateTime(timezone=True)),
        Column("completed_at", DateTime(timezone=True)),
    )
    prompt_history = Table(
        "prompt_history",
        metadata,
        Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
        Column(
            "generation_job_id",
            UUID(as_uuid=True),
            ForeignKey(f"{schema}.generation_jobs.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        Column("account_id", String(128), nullable=False),
        Column("user_id", String(128), nullable=False),
        Column("model", String(255), nullable=False),
        Column("prompt", Text, nullable=False),
        Column("response_text", Text, nullable=False),
        Column("prompt_tokens", Integer),
        Column("completion_tokens", Integer),
        Column("total_tokens", Integer),
        Column("cost", Numeric(18, 8)),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    )
    image_generation_jobs = Table(
        "image_generation_jobs",
        metadata,
        Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
        Column("account_id", String(128), nullable=False),
        Column("user_id", String(128), nullable=False),
        Column("source_generation_job_id", UUID(as_uuid=True), ForeignKey(f"{schema}.generation_jobs.id", ondelete="SET NULL")),
        Column("provider", String(64), nullable=False),
        Column("model", String(255), nullable=False),
        Column("prompt", Text, nullable=False),
        Column("source_text", Text, nullable=False),
        Column("status", String(24), nullable=False, server_default=text("'queued'")),
        Column("image_url", Text),
        Column("width", Integer),
        Column("height", Integer),
        Column("seed", Integer),
        Column("error_reason", Text),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
        Column("completed_at", DateTime(timezone=True)),
    )
    Index("ix_generation_jobs_account_created", generation_jobs.c.account_id, generation_jobs.c.created_at)
    Index("ix_generation_jobs_status_created", generation_jobs.c.status, generation_jobs.c.created_at)
    Index("ix_prompt_history_account_created", prompt_history.c.account_id, prompt_history.c.created_at)
    Index("ix_image_generation_jobs_account_created", image_generation_jobs.c.account_id, image_generation_jobs.c.created_at)
    return metadata
