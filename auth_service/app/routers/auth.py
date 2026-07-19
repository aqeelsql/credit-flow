from datetime import datetime, timezone
import asyncio
import logging
import uuid

from fastapi import APIRouter, Body, Depends, Request, Response

from app.accounts import create_individual_account, resolve_account_role
from app.config import Settings
from app.database import Database
from app.dependencies import (
    current_principal,
    database_dep,
    publisher_dep,
    redis_dep,
    require_superadmin,
    settings_dep,
)
from app.errors import AuthError
from app.events import EventPublisher
from app.models import TokenStatus, UserStatus
from app.redis_state import RedisState
from app.repository import AuthRepository
from app.schemas import (
    ForgotPasswordRequest,
    LoginRequest,
    LogoutRequest,
    Principal,
    RefreshRequest,
    ResetPasswordRequest,
    RevokeSessionRequest,
    SessionRow,
    SignupRequest,
    SignupResponse,
    SwitchAccountRequest,
    TokenResponse,
    VerifyEmailRequest,
)
from app.security import expires_in, hash_password, random_numeric_otp, random_token_urlsafe, sha256_hex, utcnow, verify_password
from app.tokens import create_access_token

router = APIRouter(tags=["auth"])


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def _is_expired(expires_at: datetime) -> bool:
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at <= utcnow()


def _refresh_from_request(request: Request, settings: Settings, body_value: str | None) -> str:
    token = body_value or request.cookies.get(settings.refresh_cookie_name)
    if not token:
        raise AuthError("missing_refresh_token", "Refresh token is required.", 401)
    return token


def _set_refresh_cookie(response: Response, settings: Settings, refresh_token: str) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=refresh_token,
        max_age=settings.refresh_token_ttl_seconds,
        httponly=True,
        secure=settings.secure_cookie,
        samesite="lax",
        path="/",
    )


def _delete_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(settings.refresh_cookie_name, path="/")


async def _publish_event(
    publisher: EventPublisher,
    routing_key: str,
    payload: dict,
    settings: Settings,
    *,
    required: bool = False,
) -> None:
    is_local = settings.environment.lower() in {"local", "dev", "development", "test"}
    try:
        if is_local and not required:
            await asyncio.wait_for(publisher.publish(routing_key, payload), timeout=1.0)
        else:
            await publisher.publish(routing_key, payload)
    except (AuthError, TimeoutError, OSError) as exc:
        if is_local and not required:
            logging.warning("Skipped %s publish in local development: %s", routing_key, exc)
            return
        raise AuthError(
            "event_publish_failed",
            f"Unable to queue required {routing_key} notification. Ensure RabbitMQ and the notification service are running.",
            503,
        ) from exc


async def _issue_session(
    repo: AuthRepository,
    redis_state: RedisState,
    settings: Settings,
    user_id: str,
    account_id: str,
    role: str,
    email: str | None = None,
) -> tuple[TokenResponse, str]:
    access_token, jti, _access_expires_at = create_access_token(settings, user_id, account_id, role, email=email)
    refresh_token = random_token_urlsafe(48)
    refresh_expires_at = expires_in(settings.refresh_token_ttl_seconds)
    await repo.create_refresh_token(
        user_id=user_id,
        account_id=account_id,
        role=role,
        jti=jti,
        token_hash=sha256_hex(refresh_token),
        expires_at=refresh_expires_at,
    )
    await redis_state.mark_jti_active(jti, user_id, account_id, role, settings.access_token_ttl_seconds)
    return (
        TokenResponse(
            access_token=access_token,
            expires_in=settings.access_token_ttl_seconds,
            user_id=user_id,
            account_id=account_id,
            role=role,
            jti=jti,
        ),
        refresh_token,
    )


@router.post("/signup", response_model=SignupResponse, status_code=201)
async def signup(
    payload: SignupRequest,
    settings: Settings = Depends(settings_dep),
    db: Database = Depends(database_dep),
    publisher: EventPublisher = Depends(publisher_dep),
) -> SignupResponse:
    password_hash = hash_password(payload.password, settings.bcrypt_rounds)
    verification_token = random_token_urlsafe(48)
    created = True
    async with db.transaction() as conn:
        repo = AuthRepository(conn)
        existing = await repo.get_user_by_email(payload.email)
        if existing is not None:
            if existing["status"] == UserStatus.ACTIVE.value:
                raise AuthError("email_already_registered", "An account already exists for this email. Please log in instead.", 409)
            if existing["status"] != UserStatus.PENDING_VERIFICATION.value:
                raise AuthError("account_disabled", "This account cannot sign up again. Contact support.", 403)
            user = existing
            created = False
        else:
            user = await repo.create_user_with_credential(payload.email, password_hash)
        await repo.create_email_verification_token(user["id"], sha256_hex(verification_token), expires_in(settings.email_verification_ttl_seconds))

    account = await create_individual_account(settings, user["id"], user["email"], payload.account_name)
    verification_url = f"{settings.frontend_base_url.rstrip('/')}/verify-email?token={verification_token}"

    await _publish_event(
        publisher,
        "user.registered",
        {
            "event_id": f"user.registered:{uuid.uuid4()}",
            "user_id": user["id"],
            "email": user["email"],
            "account_id": account.get("id"),
            "account_name": account.get("name") or payload.account_name,
            "verification_token": verification_token,
            "verification_url": verification_url,
            "verification_expires_in": settings.email_verification_ttl_seconds,
        },
        settings,
        required=True,
    )
    return SignupResponse(
        status="pending_verification",
        user_id=user["id"],
        account_id=account.get("id"),
        message="Account created. Check your email to verify your account before logging in." if created else "Verification email sent again. Check your inbox before logging in.",
    )


@router.post("/verify-email")
async def verify_email(payload: VerifyEmailRequest, db: Database = Depends(database_dep)) -> dict:
    async with db.transaction() as conn:
        repo = AuthRepository(conn)
        user = await repo.verify_email_token(sha256_hex(payload.token))
    return {"status": "verified", "user_id": user["id"], "email": user["email"]}


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    settings: Settings = Depends(settings_dep),
    db: Database = Depends(database_dep),
    redis_state: RedisState = Depends(redis_dep),
    publisher: EventPublisher = Depends(publisher_dep),
) -> TokenResponse:
    ip = _client_ip(request)
    attempts = await redis_state.increment_login_attempts(payload.email, ip)
    if attempts > settings.login_rate_limit_max_attempts:
        raise AuthError("login_rate_limited", "Too many login attempts. Try again later.", 429)

    async with db.acquire() as conn:
        repo = AuthRepository(conn)
        user = await repo.get_user_by_email(payload.email)

    if user is None or not user.get("password_hash") or not verify_password(payload.password, user["password_hash"]):
        raise AuthError("invalid_credentials", "Email or password is incorrect.", 401)
    if user["status"] == UserStatus.PENDING_VERIFICATION.value:
        raise AuthError("email_not_verified", "Please verify your email before logging in.", 403)
    if user["status"] != UserStatus.ACTIVE.value:
        raise AuthError("account_disabled", "This account cannot sign in.", 403)

    if user["email"].lower() in settings.superadmin_email_set:
        account_id, role = "platform", "SuperAdmin"
    else:
        try:
            account_id, role = await resolve_account_role(settings, user["id"], payload.account_id)
        except AuthError as exc:
            if exc.code != "account_membership_missing" or payload.account_id:
                raise
            account = await create_individual_account(settings, user["id"], user["email"])
            account_id = str(account.get("id"))
            role = str(account.get("role") or "Owner")
    async with db.transaction() as conn:
        repo = AuthRepository(conn)
        token_response, refresh_token = await _issue_session(repo, redis_state, settings, user["id"], account_id, role, email=user["email"])

    await redis_state.clear_login_attempts(payload.email, ip)
    _set_refresh_cookie(response, settings, refresh_token)
    await _publish_event(
        publisher,
        "user.logged_in",
        {"user_id": user["id"], "email": user["email"], "account_id": account_id, "role": role, "jti": token_response.jti},
        settings,
    )
    return token_response


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    payload: RefreshRequest | None = Body(default=None),
    settings: Settings = Depends(settings_dep),
    db: Database = Depends(database_dep),
    redis_state: RedisState = Depends(redis_dep),
) -> TokenResponse:
    raw_refresh_token = _refresh_from_request(request, settings, payload.refresh_token if payload else None)
    token_hash = sha256_hex(raw_refresh_token)
    async with db.transaction() as conn:
        repo = AuthRepository(conn)
        session = await repo.get_refresh_token(token_hash)
        if session is None or session["status"] != TokenStatus.ACTIVE.value:
            raise AuthError("invalid_refresh_token", "Refresh token is invalid.", 401)
        if _is_expired(session["expires_at"]) or session["user_status"] != UserStatus.ACTIVE.value:
            await repo.revoke_refresh_token_id(session["id"])
            raise AuthError("invalid_refresh_token", "Refresh token is expired or inactive.", 401)

        await repo.revoke_refresh_token_id(session["id"])
        token_response, next_refresh_token = await _issue_session(
            repo,
            redis_state,
            settings,
            session["user_id"],
            session["account_id"],
            session["role"],
            email=session.get("email"),
        )

    await redis_state.revoke_jti(session["jti"], settings.access_token_ttl_seconds)
    _set_refresh_cookie(response, settings, next_refresh_token)
    return token_response


@router.post("/switch-account", response_model=TokenResponse)
async def switch_account(
    payload: SwitchAccountRequest,
    response: Response,
    principal: Principal = Depends(current_principal),
    settings: Settings = Depends(settings_dep),
    db: Database = Depends(database_dep),
    redis_state: RedisState = Depends(redis_dep),
) -> TokenResponse:
    account_id, role = await resolve_account_role(settings, principal.user_id, payload.account_id)
    async with db.transaction() as conn:
        repo = AuthRepository(conn)
        token_response, refresh_token = await _issue_session(repo, redis_state, settings, principal.user_id, account_id, role, email=principal.email)
    await redis_state.revoke_jti(principal.jti, settings.access_token_ttl_seconds)
    _set_refresh_cookie(response, settings, refresh_token)
    return token_response


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    payload: LogoutRequest | None = Body(default=None),
    settings: Settings = Depends(settings_dep),
    db: Database = Depends(database_dep),
    redis_state: RedisState = Depends(redis_dep),
) -> dict:
    raw_refresh_token = payload.refresh_token if payload else None
    raw_refresh_token = raw_refresh_token or request.cookies.get(settings.refresh_cookie_name)
    if raw_refresh_token:
        async with db.transaction() as conn:
            repo = AuthRepository(conn)
            revoked = await repo.revoke_refresh_token_hash(sha256_hex(raw_refresh_token))
        if revoked:
            await redis_state.revoke_jti(revoked["jti"], settings.access_token_ttl_seconds)
    _delete_refresh_cookie(response, settings)
    return {"status": "logged_out"}


@router.post("/revoke")
async def revoke_session(
    payload: RevokeSessionRequest,
    _principal: Principal = Depends(require_superadmin),
    settings: Settings = Depends(settings_dep),
    db: Database = Depends(database_dep),
    redis_state: RedisState = Depends(redis_dep),
) -> dict:
    async with db.transaction() as conn:
        repo = AuthRepository(conn)
        rows = await repo.revoke_session_jti(payload.jti)
    await redis_state.revoke_jti(payload.jti, settings.access_token_ttl_seconds)
    return {"status": "revoked", "sessions_revoked": len(rows)}


@router.get("/sessions", response_model=list[SessionRow])
async def list_sessions(
    _principal: Principal = Depends(require_superadmin),
    db: Database = Depends(database_dep),
) -> list[SessionRow]:
    async with db.acquire() as conn:
        repo = AuthRepository(conn)
        rows = await repo.list_active_sessions()
    return [SessionRow(**{**row, "expires_at": row["expires_at"].isoformat()}) for row in rows]


@router.post("/forgot-password/request")
async def forgot_password_request(
    payload: ForgotPasswordRequest,
    settings: Settings = Depends(settings_dep),
    db: Database = Depends(database_dep),
    publisher: EventPublisher = Depends(publisher_dep),
) -> dict:
    otp = random_numeric_otp(settings.password_reset_otp_length)
    user = None
    async with db.transaction() as conn:
        repo = AuthRepository(conn)
        user = await repo.get_user_by_email(payload.email)
        if user is not None:
            await repo.create_password_reset_otp(user["id"], sha256_hex(otp), expires_in(settings.password_reset_otp_ttl_seconds))

    if user is not None:
        await _publish_event(
            publisher,
            "user.password_reset_requested",
            {
                "user_id": user["id"],
                "email": user["email"],
                "otp": otp,
                "otp_expires_in": settings.password_reset_otp_ttl_seconds,
            },
            settings,
        )
    return {"status": "accepted", "message": "If the email exists, a reset code will be sent."}


@router.post("/forgot-password/reset")
async def forgot_password_reset(
    payload: ResetPasswordRequest,
    settings: Settings = Depends(settings_dep),
    db: Database = Depends(database_dep),
    redis_state: RedisState = Depends(redis_dep),
) -> dict:
    new_hash = hash_password(payload.password, settings.bcrypt_rounds)
    async with db.transaction() as conn:
        repo = AuthRepository(conn)
        user, revoked = await repo.reset_password_with_otp(payload.email, sha256_hex(payload.otp), new_hash)

    for session in revoked:
        await redis_state.revoke_jti(session["jti"], settings.access_token_ttl_seconds)
    return {"status": "password_reset", "user_id": user["id"]}


@router.get("/me")
async def me(principal: Principal = Depends(current_principal)) -> dict:
    return principal.model_dump()












