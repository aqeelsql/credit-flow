import uuid
from datetime import datetime, timezone
from typing import Any

import asyncpg

from app.errors import AuthError
from app.models import TokenStatus, UserStatus
from app.security import utcnow


def _as_dict(row: asyncpg.Record | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def _uuid(value: str | uuid.UUID) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def _is_expired(expires_at: datetime) -> bool:
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at <= utcnow()


class AuthRepository:
    def __init__(self, conn: asyncpg.Connection):
        self.conn = conn

    async def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        row = await self.conn.fetchrow(
            """
            SELECT
                u.id::text AS id,
                u.name,
                u.email,
                u.status::text AS status,
                u.email_verified_at,
                c.password_hash
            FROM users u
            LEFT JOIN credentials c ON c.user_id = u.id
            WHERE u.email = $1
            """,
            email.lower(),
        )
        return _as_dict(row)

    async def get_user_by_id(self, user_id: str) -> dict[str, Any] | None:
        row = await self.conn.fetchrow(
            """
            SELECT id::text AS id, name, email, status::text AS status, email_verified_at
            FROM users
            WHERE id = $1
            """,
            _uuid(user_id),
        )
        return _as_dict(row)

    async def create_user_with_credential(self, email: str, password_hash: str, *, name: str | None = None, active: bool = False) -> dict[str, Any]:
        user_id = uuid.uuid4()
        credential_id = uuid.uuid4()
        now = utcnow()
        status = UserStatus.ACTIVE.value if active else UserStatus.PENDING_VERIFICATION.value
        email_verified_at = now if active else None
        try:
            user = await self.conn.fetchrow(
                """
                INSERT INTO users (id, name, email, status, email_verified_at, created_at, updated_at)
                VALUES ($1, $2, $3, $4::user_status, $5, $6, $6)
                RETURNING id::text AS id, name, email, status::text AS status, email_verified_at, created_at
                """,
                user_id,
                name.strip() if name else None,
                email.lower(),
                status,
                email_verified_at,
                now,
            )
            await self.conn.execute(
                """
                INSERT INTO credentials (id, user_id, password_hash, password_changed_at, created_at)
                VALUES ($1, $2, $3, $4, $4)
                """,
                credential_id,
                user_id,
                password_hash,
                now,
            )
        except asyncpg.UniqueViolationError as exc:
            raise AuthError("email_already_registered", "An account already exists for this email.", 409) from exc
        if user is None:
            raise AuthError("signup_failed", "Unable to create the user account.", 500)
        return dict(user)

    async def update_user_name(self, user_id: str, name: str) -> None:
        await self.conn.execute(
            """
            UPDATE users
            SET name = $1, updated_at = $2
            WHERE id = $3
            """,
            name.strip(),
            utcnow(),
            _uuid(user_id),
        )

    async def activate_user(self, user_id: str) -> dict[str, Any]:
        now = utcnow()
        user = await self.conn.fetchrow(
            """
            UPDATE users
            SET status = $1::user_status,
                email_verified_at = COALESCE(email_verified_at, $2),
                updated_at = $2
            WHERE id = $3
            RETURNING id::text AS id, email, status::text AS status, email_verified_at
            """,
            UserStatus.ACTIVE.value,
            now,
            _uuid(user_id),
        )
        if user is None:
            raise AuthError("activation_failed", "Unable to activate account.", 500)
        return dict(user)

    async def set_user_password(self, user_id: str, password_hash: str) -> None:
        await self.conn.execute(
            """
            INSERT INTO credentials (id, user_id, password_hash, password_changed_at, created_at)
            VALUES ($1, $2, $3, $4, $4)
            ON CONFLICT (user_id)
            DO UPDATE SET password_hash = EXCLUDED.password_hash, password_changed_at = EXCLUDED.password_changed_at
            """,
            uuid.uuid4(),
            _uuid(user_id),
            password_hash,
            utcnow(),
        )

    async def create_email_verification_token(self, user_id: str, token_hash: str, expires_at: datetime) -> dict[str, Any]:
        row = await self.conn.fetchrow(
            """
            INSERT INTO email_verification_tokens (id, user_id, token_hash, status, expires_at, created_at)
            VALUES ($1, $2, $3, $4::token_status, $5, $6)
            RETURNING id::text AS id, user_id::text AS user_id, expires_at
            """,
            uuid.uuid4(),
            _uuid(user_id),
            token_hash,
            TokenStatus.ACTIVE.value,
            expires_at,
            utcnow(),
        )
        if row is None:
            raise AuthError("verification_token_failed", "Unable to create verification token.", 500)
        return dict(row)

    async def verify_email_token(self, token_hash: str) -> dict[str, Any]:
        row = await self.conn.fetchrow(
            """
            SELECT
                evt.id::text AS token_id,
                evt.user_id::text AS user_id,
                evt.status::text AS token_status,
                evt.expires_at,
                u.email,
                u.status::text AS user_status
            FROM email_verification_tokens evt
            JOIN users u ON u.id = evt.user_id
            WHERE evt.token_hash = $1
            ORDER BY evt.created_at DESC
            LIMIT 1
            FOR UPDATE OF evt, u
            """,
            token_hash,
        )
        if row is None or row["token_status"] != TokenStatus.ACTIVE.value or _is_expired(row["expires_at"]):
            raise AuthError("invalid_verification_token", "Email verification token is invalid or expired.", 400)

        now = utcnow()
        await self.conn.execute(
            """
            UPDATE email_verification_tokens
            SET status = $1::token_status, used_at = $2
            WHERE id = $3
            """,
            TokenStatus.USED.value,
            now,
            _uuid(row["token_id"]),
        )
        user = await self.conn.fetchrow(
            """
            UPDATE users
            SET status = $1::user_status, email_verified_at = COALESCE(email_verified_at, $2), updated_at = $2
            WHERE id = $3
            RETURNING id::text AS id, email, status::text AS status, email_verified_at
            """,
            UserStatus.ACTIVE.value,
            now,
            _uuid(row["user_id"]),
        )
        if user is None:
            raise AuthError("verification_failed", "Unable to activate account.", 500)
        return dict(user)

    async def create_refresh_token(
        self,
        user_id: str,
        account_id: str,
        role: str,
        jti: str,
        token_hash: str,
        expires_at: datetime,
    ) -> dict[str, Any]:
        row = await self.conn.fetchrow(
            """
            INSERT INTO refresh_tokens (id, user_id, account_id, role, jti, token_hash, status, expires_at, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7::token_status, $8, $9)
            RETURNING id::text AS id, user_id::text AS user_id, account_id, role, jti, expires_at, status::text AS status
            """,
            uuid.uuid4(),
            _uuid(user_id),
            account_id,
            role,
            jti,
            token_hash,
            TokenStatus.ACTIVE.value,
            expires_at,
            utcnow(),
        )
        if row is None:
            raise AuthError("refresh_token_failed", "Unable to create refresh token.", 500)
        return dict(row)

    async def get_refresh_token(self, token_hash: str) -> dict[str, Any] | None:
        row = await self.conn.fetchrow(
            """
            SELECT
                rt.id::text AS id,
                rt.user_id::text AS user_id,
                rt.account_id,
                rt.role,
                rt.jti,
                rt.status::text AS status,
                rt.expires_at,
                u.status::text AS user_status,
                u.email
            FROM refresh_tokens rt
            JOIN users u ON u.id = rt.user_id
            WHERE rt.token_hash = $1
            """,
            token_hash,
        )
        return _as_dict(row)

    async def revoke_refresh_token_hash(self, token_hash: str) -> dict[str, Any] | None:
        row = await self.conn.fetchrow(
            """
            UPDATE refresh_tokens
            SET status = $1::token_status, revoked_at = $2
            WHERE token_hash = $3 AND status = $4::token_status
            RETURNING id::text AS id, user_id::text AS user_id, jti, expires_at
            """,
            TokenStatus.REVOKED.value,
            utcnow(),
            token_hash,
            TokenStatus.ACTIVE.value,
        )
        return _as_dict(row)

    async def revoke_refresh_token_id(self, token_id: str) -> dict[str, Any] | None:
        row = await self.conn.fetchrow(
            """
            UPDATE refresh_tokens
            SET status = $1::token_status, revoked_at = $2
            WHERE id = $3 AND status = $4::token_status
            RETURNING id::text AS id, user_id::text AS user_id, jti, expires_at
            """,
            TokenStatus.REVOKED.value,
            utcnow(),
            _uuid(token_id),
            TokenStatus.ACTIVE.value,
        )
        return _as_dict(row)

    async def revoke_session_jti(self, jti: str) -> list[dict[str, Any]]:
        rows = await self.conn.fetch(
            """
            UPDATE refresh_tokens
            SET status = $1::token_status, revoked_at = $2
            WHERE jti = $3 AND status = $4::token_status
            RETURNING id::text AS id, user_id::text AS user_id, jti, expires_at
            """,
            TokenStatus.REVOKED.value,
            utcnow(),
            jti,
            TokenStatus.ACTIVE.value,
        )
        return [dict(row) for row in rows]

    async def revoke_all_refresh_tokens_for_user(self, user_id: str) -> list[dict[str, Any]]:
        rows = await self.conn.fetch(
            """
            UPDATE refresh_tokens
            SET status = $1::token_status, revoked_at = $2
            WHERE user_id = $3 AND status = $4::token_status
            RETURNING id::text AS id, user_id::text AS user_id, jti, expires_at
            """,
            TokenStatus.REVOKED.value,
            utcnow(),
            _uuid(user_id),
            TokenStatus.ACTIVE.value,
        )
        return [dict(row) for row in rows]

    async def list_active_sessions(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = await self.conn.fetch(
            """
            SELECT
                jti,
                user_id::text AS user_id,
                account_id,
                role,
                expires_at,
                status::text AS status
            FROM refresh_tokens
            WHERE status = $1::token_status AND expires_at > $2
            ORDER BY created_at DESC
            LIMIT $3
            """,
            TokenStatus.ACTIVE.value,
            utcnow(),
            limit,
        )
        return [dict(row) for row in rows]

    async def create_password_reset_otp(self, user_id: str, otp_hash: str, expires_at: datetime) -> dict[str, Any]:
        row = await self.conn.fetchrow(
            """
            INSERT INTO password_reset_tokens (id, user_id, otp_hash, status, expires_at, created_at)
            VALUES ($1, $2, $3, $4::token_status, $5, $6)
            RETURNING id::text AS id, user_id::text AS user_id, expires_at
            """,
            uuid.uuid4(),
            _uuid(user_id),
            otp_hash,
            TokenStatus.ACTIVE.value,
            expires_at,
            utcnow(),
        )
        if row is None:
            raise AuthError("password_reset_failed", "Unable to create password reset OTP.", 500)
        return dict(row)

    async def reset_password_with_otp(self, email: str, otp_hash: str, password_hash: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        user = await self.get_user_by_email(email)
        if user is None:
            raise AuthError("invalid_password_reset", "Password reset OTP is invalid or expired.", 400)

        token = await self.conn.fetchrow(
            """
            SELECT id::text AS id, user_id::text AS user_id, status::text AS status, expires_at
            FROM password_reset_tokens
            WHERE user_id = $1 AND otp_hash = $2
            ORDER BY created_at DESC
            LIMIT 1
            FOR UPDATE
            """,
            _uuid(user["id"]),
            otp_hash,
        )
        if token is None or token["status"] != TokenStatus.ACTIVE.value or _is_expired(token["expires_at"]):
            raise AuthError("invalid_password_reset", "Password reset OTP is invalid or expired.", 400)

        now = utcnow()
        await self.conn.execute(
            """
            UPDATE password_reset_tokens
            SET status = $1::token_status, used_at = $2
            WHERE id = $3
            """,
            TokenStatus.USED.value,
            now,
            _uuid(token["id"]),
        )
        await self.conn.execute(
            """
            INSERT INTO credentials (id, user_id, password_hash, password_changed_at, created_at)
            VALUES ($1, $2, $3, $4, $4)
            ON CONFLICT (user_id)
            DO UPDATE SET password_hash = EXCLUDED.password_hash, password_changed_at = EXCLUDED.password_changed_at
            """,
            uuid.uuid4(),
            _uuid(user["id"]),
            password_hash,
            now,
        )
        revoked = await self.revoke_all_refresh_tokens_for_user(user["id"])
        return user, revoked








