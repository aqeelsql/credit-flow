import uuid
from datetime import datetime, timezone

import jwt
from jwt import ExpiredSignatureError, InvalidTokenError

from app.config import Settings
from app.errors import AuthError
from app.schemas import Principal
from app.security import utcnow


def create_access_token(
    settings: Settings,
    user_id: str,
    account_id: str,
    role: str,
    jti: str | None = None,
    email: str | None = None,
) -> tuple[str, str, datetime]:
    token_jti = jti or str(uuid.uuid4())
    expires_at = utcnow().timestamp() + settings.access_token_ttl_seconds
    payload = {
        "user_id": user_id,
        "sub": user_id,
        "account_id": account_id,
        "role": role,
        "jti": token_jti,
        "iss": settings.jwt_issuer,
        "iat": int(utcnow().timestamp()),
        "exp": int(expires_at),
    }
    if email:
        payload["email"] = email
    if settings.jwt_audience:
        payload["aud"] = settings.jwt_audience
    token = jwt.encode(payload, settings.jwt_signing_key, algorithm=settings.jwt_algorithm)
    return token, token_jti, datetime.fromtimestamp(expires_at, tz=timezone.utc)


def decode_access_token(settings: Settings, token: str) -> Principal:
    audience = settings.jwt_audience or None
    options = {
        "verify_aud": audience is not None,
        "verify_iss": True,
    }
    try:
        claims = jwt.decode(
            token,
            settings.jwt_verification_key,
            algorithms=[settings.jwt_algorithm],
            audience=audience,
            issuer=settings.jwt_issuer,
            options=options,
        )
    except ExpiredSignatureError as exc:
        raise AuthError("token_expired", "Access token has expired.", 401) from exc
    except InvalidTokenError as exc:
        raise AuthError("invalid_token", "Access token is invalid.", 401) from exc

    user_id = claims.get("user_id") or claims.get("sub")
    account_id = claims.get("account_id")
    role = claims.get("role")
    jti = claims.get("jti")
    if not all([user_id, account_id, role, jti]):
        raise AuthError("invalid_token_claims", "Access token is missing required claims.", 401)
    return Principal(
        user_id=str(user_id),
        account_id=str(account_id),
        role=str(role),
        jti=str(jti),
        email=str(claims["email"]) if claims.get("email") else None,
    )


def bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthError("missing_token", "Bearer token is required.", 401)
    return authorization.removeprefix("Bearer ").strip()

