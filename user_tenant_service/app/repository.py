from datetime import datetime, timedelta, timezone
from typing import Any
import hashlib
import secrets
import uuid

import asyncpg

from app.config import Settings
from app.errors import AccountError
from app.models import AccountRole, AccountType, InviteStatus, MemberStatus


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def expires_in(seconds: int) -> datetime:
    return utcnow() + timedelta(seconds=seconds)


def hash_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def random_invite_code() -> str:
    return secrets.token_urlsafe(24)


def _uuid(value: str | uuid.UUID) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def _as_dict(row: asyncpg.Record | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


class AccountRepository:
    def __init__(self, conn: asyncpg.Connection, settings: Settings):
        self.conn = conn
        self.settings = settings

    async def list_user_memberships(self, user_id: str) -> list[dict[str, Any]]:
        rows = await self.conn.fetch(
            """
            SELECT
                m.id::text AS id,
                m.account_id::text AS account_id,
                a.name AS account_name,
                a.type::text AS account_type,
                m.role::text AS role,
                m.status::text AS status,
                a.plan,
                a.credits,
                COALESCE(active_members.team_size, 0)::int AS team_size
            FROM account_members m
            JOIN accounts a ON a.id = m.account_id
            LEFT JOIN LATERAL (
                SELECT count(*) AS team_size
                FROM account_members tm
                WHERE tm.account_id = a.id AND tm.status = 'active'::member_status
            ) active_members ON true
            WHERE m.user_id = $1 AND m.status = 'active'::member_status
            ORDER BY a.created_at ASC
            """,
            _uuid(user_id),
        )
        return [dict(row) for row in rows]

    async def create_account_with_owner(
        self,
        user_id: str,
        email: str,
        account_type: AccountType,
        name: str,
    ) -> dict[str, Any]:
        account_id = uuid.uuid4()
        now = utcnow()
        row = await self.conn.fetchrow(
            """
            INSERT INTO accounts (id, name, type, plan, credits, created_by_user_id, created_at, updated_at)
            VALUES ($1, $2, $3::account_type, $4, $5, $6, $7, $7)
            RETURNING id::text AS id, name, type::text AS type, plan, credits
            """,
            account_id,
            name,
            account_type.value,
            self.settings.default_plan,
            self.settings.default_credits,
            _uuid(user_id),
            now,
        )
        member_row = await self.conn.fetchrow(
            """
            INSERT INTO account_members (id, account_id, user_id, email, role, status, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5::account_role, $6::member_status, $7, $7)
            RETURNING id::text AS member_id
            """,
            uuid.uuid4(),
            account_id,
            _uuid(user_id),
            email.lower(),
            AccountRole.OWNER.value,
            MemberStatus.ACTIVE.value,
            now,
        )
        if row is None or member_row is None:
            raise AccountError("account_create_failed", "Unable to create account.", 500)
        result = dict(row)
        result["role"] = AccountRole.OWNER.value
        result["team_size"] = 1
        result["member_id"] = member_row["member_id"]
        result["_created"] = True
        return result

    async def ensure_individual_account(self, user_id: str, email: str, account_name: str | None = None) -> dict[str, Any]:
        existing = await self.conn.fetchrow(
            """
            SELECT
                a.id::text AS id,
                a.name,
                a.type::text AS type,
                a.plan,
                a.credits,
                m.id::text AS member_id,
                m.role::text AS role,
                COALESCE(active_members.team_size, 0)::int AS team_size
            FROM account_members m
            JOIN accounts a ON a.id = m.account_id
            LEFT JOIN LATERAL (
                SELECT count(*) AS team_size
                FROM account_members tm
                WHERE tm.account_id = a.id AND tm.status = 'active'::member_status
            ) active_members ON true
            WHERE m.user_id = $1
              AND m.role = 'Owner'::account_role
              AND m.status = 'active'::member_status
              AND a.type = 'individual'::account_type
            ORDER BY a.created_at ASC
            LIMIT 1
            """,
            _uuid(user_id),
        )
        if existing:
            result = dict(existing)
            result["_created"] = False
            return result
        default_name = account_name or f"{email.split('@', 1)[0]}'s Studio"
        return await self.create_account_with_owner(user_id, email, AccountType.INDIVIDUAL, default_name)

    async def get_active_membership(self, account_id: str, user_id: str) -> dict[str, Any] | None:
        row = await self.conn.fetchrow(
            """
            SELECT id::text AS id, account_id::text AS account_id, user_id::text AS user_id, email, role::text AS role, status::text AS status
            FROM account_members
            WHERE account_id = $1 AND user_id = $2 AND status = 'active'::member_status
            """,
            _uuid(account_id),
            _uuid(user_id),
        )
        return _as_dict(row)

    async def list_team_members(self, account_id: str) -> list[dict[str, Any]]:
        rows = await self.conn.fetch(
            """
            SELECT
                id::text AS id,
                user_id::text AS user_id,
                split_part(email, '@', 1) AS name,
                email,
                role::text AS role,
                status::text AS status
            FROM account_members
            WHERE account_id = $1 AND status <> 'removed'::member_status
            ORDER BY created_at ASC
            """,
            _uuid(account_id),
        )
        return [dict(row) for row in rows]

    async def account_summary(self, account_id: str) -> dict[str, Any] | None:
        row = await self.conn.fetchrow(
            """
            SELECT
                a.id::text AS id,
                a.name,
                a.type::text AS type,
                a.plan,
                a.credits,
                COALESCE(active_members.team_size, 0)::int AS team_size
            FROM accounts a
            LEFT JOIN LATERAL (
                SELECT count(*) AS team_size
                FROM account_members tm
                WHERE tm.account_id = a.id AND tm.status = 'active'::member_status
            ) active_members ON true
            WHERE a.id = $1
            """,
            _uuid(account_id),
        )
        return _as_dict(row)

    async def create_invite(self, account_id: str, email: str, role: AccountRole, created_by_user_id: str) -> tuple[dict[str, Any], str]:
        if role == AccountRole.OWNER:
            raise AccountError("invalid_invite_role", "Owner role cannot be granted by invite.", 400)
        code = random_invite_code()
        row = await self.conn.fetchrow(
            """
            WITH created AS (
                INSERT INTO invites (id, account_id, email, role, code_hash, status, created_by_user_id, expires_at, created_at)
                VALUES ($1, $2, $3, $4::account_role, $5, $6::invite_status, $7, $8, $9)
                RETURNING id, account_id, email, role, expires_at
            )
            SELECT
                created.id::text AS invite_id,
                created.account_id::text AS account_id,
                accounts.name AS account_name,
                created.email,
                created.role::text AS role,
                created.expires_at
            FROM created
            JOIN accounts ON accounts.id = created.account_id
            """,
            uuid.uuid4(),
            _uuid(account_id),
            email.lower(),
            role.value,
            hash_code(code),
            InviteStatus.PENDING.value,
            _uuid(created_by_user_id),
            expires_in(self.settings.invite_ttl_seconds),
            utcnow(),
        )
        if row is None:
            raise AccountError("invite_create_failed", "Unable to create invite.", 500)
        return dict(row), code

    async def accept_invite(self, code: str, user_id: str, user_email: str | None) -> dict[str, Any]:
        invite = await self.conn.fetchrow(
            """
            SELECT id::text AS id, account_id::text AS account_id, email, role::text AS role, status::text AS status, expires_at
            FROM invites
            WHERE code_hash = $1
            ORDER BY created_at DESC
            LIMIT 1
            FOR UPDATE
            """,
            hash_code(code),
        )
        if invite is None or invite["status"] != InviteStatus.PENDING.value:
            raise AccountError("invalid_invite", "Invite code is invalid.", 400)
        if not user_email:
            raise AccountError("invite_email_required", "Authenticated user email is required to accept an invite.", 403)
        if invite["email"].lower() != user_email.lower():
            raise AccountError("invite_email_mismatch", "This invite was sent to a different email address.", 403)
        expires_at = invite["expires_at"]
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= utcnow():
            await self.conn.execute(
                "UPDATE invites SET status = $1::invite_status WHERE id = $2",
                InviteStatus.EXPIRED.value,
                _uuid(invite["id"]),
            )
            raise AccountError("expired_invite", "Invite code has expired.", 400)

        now = utcnow()
        try:
            member = await self.conn.fetchrow(
                """
                INSERT INTO account_members (id, account_id, user_id, email, role, status, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5::account_role, $6::member_status, $7, $7)
                ON CONFLICT (account_id, user_id)
                DO UPDATE SET
                    role = CASE
                        WHEN account_members.role = 'Owner'::account_role THEN account_members.role
                        ELSE EXCLUDED.role
                    END,
                    status = EXCLUDED.status,
                    updated_at = EXCLUDED.updated_at
                RETURNING id::text AS member_id, email, role::text AS role
                """,
                uuid.uuid4(),
                _uuid(invite["account_id"]),
                _uuid(user_id),
                invite["email"].lower(),
                invite["role"],
                MemberStatus.ACTIVE.value,
                now,
            )
        except asyncpg.ForeignKeyViolationError as exc:
            raise AccountError("account_missing", "Invite account no longer exists.", 404) from exc

        await self.conn.execute(
            """
            UPDATE invites
            SET status = $1::invite_status, accepted_by_user_id = $2, accepted_at = $3
            WHERE id = $4
            """,
            InviteStatus.ACCEPTED.value,
            _uuid(user_id),
            now,
            _uuid(invite["id"]),
        )
        account = await self.account_for_user(invite["account_id"], user_id)
        if account is None or member is None:
            raise AccountError("membership_create_failed", "Unable to activate invite membership.", 500)
        account["member_id"] = member["member_id"]
        account["invite_id"] = invite["id"]
        return account

    async def account_for_user(self, account_id: str, user_id: str) -> dict[str, Any] | None:
        row = await self.conn.fetchrow(
            """
            SELECT
                a.id::text AS id,
                a.name,
                a.type::text AS type,
                m.role::text AS role,
                a.plan,
                a.credits,
                COALESCE(active_members.team_size, 0)::int AS team_size
            FROM accounts a
            JOIN account_members m ON m.account_id = a.id
            LEFT JOIN LATERAL (
                SELECT count(*) AS team_size
                FROM account_members tm
                WHERE tm.account_id = a.id AND tm.status = 'active'::member_status
            ) active_members ON true
            WHERE a.id = $1 AND m.user_id = $2 AND m.status = 'active'::member_status
            """,
            _uuid(account_id),
            _uuid(user_id),
        )
        return _as_dict(row)

    async def update_member_role(self, account_id: str, membership_id: str, role: AccountRole) -> dict[str, Any]:
        if role == AccountRole.OWNER:
            raise AccountError("invalid_role_change", "Owner role cannot be assigned here.", 400)
        row = await self.conn.fetchrow(
            """
            UPDATE account_members
            SET role = $1::account_role, updated_at = $2
            WHERE id = $3 AND account_id = $4 AND status = 'active'::member_status AND role <> 'Owner'::account_role
            RETURNING id::text AS id, user_id::text AS user_id, split_part(email, '@', 1) AS name, email, role::text AS role, status::text AS status
            """,
            role.value,
            utcnow(),
            _uuid(membership_id),
            _uuid(account_id),
        )
        if row is None:
            raise AccountError("member_not_found", "Member was not found or cannot be changed.", 404)
        return dict(row)

    async def remove_member(self, account_id: str, membership_id: str) -> dict[str, Any]:
        row = await self.conn.fetchrow(
            """
            UPDATE account_members
            SET status = $1::member_status, updated_at = $2
            WHERE id = $3 AND account_id = $4 AND role <> 'Owner'::account_role
            RETURNING id::text AS id, user_id::text AS user_id, split_part(email, '@', 1) AS name, email, role::text AS role, status::text AS status
            """,
            MemberStatus.REMOVED.value,
            utcnow(),
            _uuid(membership_id),
            _uuid(account_id),
        )
        if row is None:
            raise AccountError("member_not_found", "Member was not found or cannot be removed.", 404)
        return dict(row)

    async def update_account_from_invoice(
        self,
        account_id: str,
        plan: str | None = None,
        credits_delta: int | None = None,
        credits: int | None = None,
    ) -> dict[str, Any] | None:
        if credits is not None:
            row = await self.conn.fetchrow(
                """
                UPDATE accounts
                SET plan = COALESCE($2, plan), credits = GREATEST($3, 0), updated_at = $4
                WHERE id = $1
                RETURNING id::text AS id
                """,
                _uuid(account_id),
                plan,
                credits,
                utcnow(),
            )
        elif credits_delta is not None:
            row = await self.conn.fetchrow(
                """
                UPDATE accounts
                SET plan = COALESCE($2, plan), credits = GREATEST(credits + $3, 0), updated_at = $4
                WHERE id = $1
                RETURNING id::text AS id
                """,
                _uuid(account_id),
                plan,
                credits_delta,
                utcnow(),
            )
        elif plan is not None:
            row = await self.conn.fetchrow(
                """
                UPDATE accounts
                SET plan = $2, updated_at = $3
                WHERE id = $1
                RETURNING id::text AS id
                """,
                _uuid(account_id),
                plan,
                utcnow(),
            )
        else:
            return await self.account_summary(account_id)

        if row is None:
            return None
        return await self.account_summary(account_id)
