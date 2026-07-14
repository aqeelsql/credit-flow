from enum import Enum

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, MetaData, String, Table, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.dialects.postgresql import UUID


class AccountType(str, Enum):
    INDIVIDUAL = "individual"
    TEAM = "team"
    PLATFORM = "platform"


class AccountRole(str, Enum):
    OWNER = "Owner"
    TENANT_ADMIN = "TenantAdmin"
    MEMBER = "Member"


class MemberStatus(str, Enum):
    ACTIVE = "active"
    INVITED = "invited"
    REMOVED = "removed"


class InviteStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REVOKED = "revoked"
    EXPIRED = "expired"


def build_metadata(schema: str) -> MetaData:
    metadata = MetaData(schema=schema)
    account_type = PgEnum(*(item.value for item in AccountType), name="account_type", schema=schema)
    account_role = PgEnum(*(item.value for item in AccountRole), name="account_role", schema=schema)
    member_status = PgEnum(*(item.value for item in MemberStatus), name="member_status", schema=schema)
    invite_status = PgEnum(*(item.value for item in InviteStatus), name="invite_status", schema=schema)

    accounts = Table(
        "accounts",
        metadata,
        Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
        Column("name", String(180), nullable=False),
        Column("type", account_type, nullable=False),
        Column("plan", String(64), nullable=False, server_default="Starter"),
        Column("credits", Integer, nullable=False, server_default="0"),
        Column("created_by_user_id", UUID(as_uuid=True), nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
        Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
        CheckConstraint("credits >= 0", name="ck_accounts_credits_nonnegative"),
    )

    account_members = Table(
        "account_members",
        metadata,
        Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
        Column("account_id", UUID(as_uuid=True), ForeignKey(f"{schema}.accounts.id", ondelete="CASCADE"), nullable=False),
        Column("user_id", UUID(as_uuid=True), nullable=False),
        Column("email", String(320), nullable=False),
        Column("role", account_role, nullable=False),
        Column("status", member_status, nullable=False, server_default=MemberStatus.ACTIVE.value),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
        Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
        UniqueConstraint("account_id", "user_id", name="uq_account_members_account_user"),
    )

    invites = Table(
        "invites",
        metadata,
        Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
        Column("account_id", UUID(as_uuid=True), ForeignKey(f"{schema}.accounts.id", ondelete="CASCADE"), nullable=False),
        Column("email", String(320), nullable=False),
        Column("role", account_role, nullable=False, server_default=AccountRole.MEMBER.value),
        Column("code_hash", Text, nullable=False, unique=True),
        Column("status", invite_status, nullable=False, server_default=InviteStatus.PENDING.value),
        Column("created_by_user_id", UUID(as_uuid=True), nullable=False),
        Column("accepted_by_user_id", UUID(as_uuid=True)),
        Column("expires_at", DateTime(timezone=True), nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
        Column("accepted_at", DateTime(timezone=True)),
        Column("revoked_at", DateTime(timezone=True)),
    )

    Index("ix_accounts_created_by", accounts.c.created_by_user_id)
    Index("ix_accounts_type", accounts.c.type)
    Index("ix_account_members_user_status", account_members.c.user_id, account_members.c.status)
    Index("ix_account_members_account_status", account_members.c.account_id, account_members.c.status)
    Index("ix_invites_account_status", invites.c.account_id, invites.c.status)
    Index("ix_invites_email_status", invites.c.email, invites.c.status)
    return metadata
