from fastapi import Depends, Header, Request

from app.config import Settings, get_settings
from app.database import Database
from app.errors import AuthError
from app.events import EventPublisher
from app.redis_state import RedisState
from app.schemas import Principal
from app.tokens import bearer_token, decode_access_token


def settings_dep() -> Settings:
    return get_settings()


def database_dep(request: Request) -> Database:
    return request.app.state.database


def redis_dep(request: Request) -> RedisState:
    return request.app.state.redis_state


def publisher_dep(request: Request) -> EventPublisher:
    return request.app.state.publisher


async def current_principal(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(settings_dep),
    redis_state: RedisState = Depends(redis_dep),
) -> Principal:
    token = bearer_token(authorization)
    principal = decode_access_token(settings, token)
    if await redis_state.is_jti_revoked(principal.jti) or not await redis_state.is_jti_active(principal.jti):
        raise AuthError("token_revoked", "Access token has been revoked or is no longer active.", 401)
    return principal


def require_superadmin(principal: Principal = Depends(current_principal)) -> Principal:
    if principal.role != "SuperAdmin":
        raise AuthError("forbidden", "SuperAdmin role is required.", 403)
    return principal

