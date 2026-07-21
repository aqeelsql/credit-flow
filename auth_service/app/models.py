from enum import Enum

from sqlalchemy import Column, DateTime, ForeignKey, Index, MetaData, String, Table, Text, text
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.dialects.postgresql import UUID


class UserStatus(str, Enum):
    PENDING_VERIFICATION = "pending_verification"
    ACTIVE = "active"
    DISABLED = "disabled"


class TokenStatus(str, Enum):
    ACTIVE = "active"
    REVOKED = "revoked"
    USED = "used"
    EXPIRED = "expired"


def build_metadata(schema: str) -> MetaData:
    metadata = MetaData(schema=schema)
    user_status = PgEnum(*(status.value for status in UserStatus), name="user_status", schema=schema)
    token_status = PgEnum(*(status.value for status in TokenStatus), name="token_status", schema=schema)

    users = Table(
        "users",
        metadata,
        Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
        Column("name", String(180)),
        Column("email", String(320), nullable=False, unique=True),
        Column("status", user_status, nullable=False, server_default=UserStatus.ACTIVE.value),
        Column("email_verified_at", DateTime(timezone=True)),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
        Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    )

    Table(
        "credentials",
        metadata,
        Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
        Column("user_id", UUID(as_uuid=True), ForeignKey(f"{schema}.users.id", ondelete="CASCADE"), nullable=False, unique=True),
        Column("password_hash", Text, nullable=False),
        Column("password_changed_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    )

    refresh_tokens = Table(
        "refresh_tokens",
        metadata,
        Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
        Column("user_id", UUID(as_uuid=True), ForeignKey(f"{schema}.users.id", ondelete="CASCADE"), nullable=False),
        Column("account_id", String(128), nullable=False),
        Column("role", String(32), nullable=False),
        Column("jti", String(128), nullable=False),
        Column("token_hash", Text, nullable=False, unique=True),
        Column("status", token_status, nullable=False, server_default=TokenStatus.ACTIVE.value),
        Column("expires_at", DateTime(timezone=True), nullable=False),
        Column("revoked_at", DateTime(timezone=True)),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    )

    password_reset_tokens = Table(
        "password_reset_tokens",
        metadata,
        Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
        Column("user_id", UUID(as_uuid=True), ForeignKey(f"{schema}.users.id", ondelete="CASCADE"), nullable=False),
        Column("otp_hash", Text, nullable=False, unique=True),
        Column("status", token_status, nullable=False, server_default=TokenStatus.ACTIVE.value),
        Column("expires_at", DateTime(timezone=True), nullable=False),
        Column("used_at", DateTime(timezone=True)),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    )

    email_verification_tokens = Table(
        "email_verification_tokens",
        metadata,
        Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
        Column("user_id", UUID(as_uuid=True), ForeignKey(f"{schema}.users.id", ondelete="CASCADE"), nullable=False),
        Column("token_hash", Text, nullable=False, unique=True),
        Column("status", token_status, nullable=False, server_default=TokenStatus.ACTIVE.value),
        Column("expires_at", DateTime(timezone=True), nullable=False),
        Column("used_at", DateTime(timezone=True)),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    )

    Index("ix_users_email", users.c.email)
    Index("ix_refresh_tokens_user_status", refresh_tokens.c.user_id, refresh_tokens.c.status)
    Index("ix_refresh_tokens_jti", refresh_tokens.c.jti)
    Index("ix_password_reset_tokens_user_status", password_reset_tokens.c.user_id, password_reset_tokens.c.status)
    Index("ix_email_verification_tokens_user_status", email_verification_tokens.c.user_id, email_verification_tokens.c.status)
    return metadata

