from fastapi import Request
from jwt import ExpiredSignatureError, InvalidTokenError, decode
from starlette import status

from app.config import Settings
from app.errors import GatewayError
from app.redis_state import RedisState
from app.schemas import Principal


AUTH_HEADER_PREFIX = "Bearer "


def extract_bearer_token(request: Request) -> str:
    value = request.headers.get("authorization") or request.headers.get("Authorization")
    if not value or not value.startswith(AUTH_HEADER_PREFIX):
        raise GatewayError("missing_token", "A bearer access token is required.", status.HTTP_401_UNAUTHORIZED)
    return value[len(AUTH_HEADER_PREFIX) :].strip()


def is_local_mock_token(token: str, settings: Settings) -> bool:
    return settings.environment.lower() in {"local", "dev", "development"} and token.endswith(".mock-signature")


async def authenticate_request(request: Request, settings: Settings, redis_state: RedisState) -> Principal:
    token = extract_bearer_token(request)
    local_mock = is_local_mock_token(token, settings)
    audience = settings.jwt_audience or None
    decode_options = {
        "verify_aud": audience is not None,
        "verify_iss": settings.jwt_issuer is not None,
    }
    try:
        if local_mock:
            claims = decode(
                token,
                options={"verify_signature": False, "verify_exp": True, "verify_aud": False, "verify_iss": False},
            )
        else:
            claims = decode(
                token,
                settings.jwt_key,
                algorithms=settings.jwt_algorithms,
                audience=audience,
                issuer=settings.jwt_issuer,
                options=decode_options,
            )
    except ExpiredSignatureError as exc:
        raise GatewayError("token_expired", "Access token has expired.", status.HTTP_401_UNAUTHORIZED) from exc
    except InvalidTokenError as exc:
        raise GatewayError("invalid_token", "Access token is invalid.", status.HTTP_401_UNAUTHORIZED) from exc

    user_id = claims.get("user_id") or claims.get("sub")
    account_id = claims.get("account_id")
    role = claims.get("role")
    jti = claims.get("jti")
    missing = [name for name, value in {"user_id": user_id, "role": role, "jti": jti}.items() if not value]
    if missing:
        raise GatewayError(
            "invalid_token_claims",
            "Access token is missing required claims.",
            status.HTTP_401_UNAUTHORIZED,
            {"missing": missing},
        )

    if not local_mock and (await redis_state.is_session_revoked(str(jti)) or not await redis_state.is_session_active(str(jti))):
        raise GatewayError("session_revoked", "Session has been revoked or is no longer active.", status.HTTP_401_UNAUTHORIZED)

    principal = Principal(
        user_id=str(user_id),
        account_id=str(account_id) if account_id else None,
        role=str(role),
        jti=str(jti),
        raw_claims=claims,
    )
    request.state.principal = principal
    return principal


def require_account(principal: Principal) -> None:
    if principal.role != "SuperAdmin" and not principal.account_id:
        raise GatewayError("missing_account_scope", "Account-scoped routes require account_id.", status.HTTP_403_FORBIDDEN)


def enforce_roles(principal: Principal, allowed_roles: set[str]) -> None:
    if principal.role not in allowed_roles:
        raise GatewayError("forbidden", "Role is not permitted for this route.", status.HTTP_403_FORBIDDEN)

