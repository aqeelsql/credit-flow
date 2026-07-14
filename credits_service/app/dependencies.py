from fastapi import Depends, Header, Request

from app.config import Settings, get_settings
from app.database import Database
from app.errors import CreditsError
from app.events import EventBus
from app.schemas import Principal

OWNER_ROLES = {"Owner"}
ACCOUNT_ROLES = {"Owner", "TenantAdmin", "Member"}


def settings_dep() -> Settings:
    return get_settings()


def database_dep(request: Request) -> Database:
    return request.app.state.database


def event_bus_dep(request: Request) -> EventBus:
    return request.app.state.event_bus


async def current_principal(
    x_user_id: str | None = Header(default=None),
    x_account_id: str | None = Header(default=None),
    x_role: str | None = Header(default=None),
    x_user_email: str | None = Header(default=None),
) -> Principal:
    if not x_user_id or not x_role:
        raise CreditsError("missing_principal", "Gateway identity headers are required.", 401)
    return Principal(user_id=x_user_id, account_id=x_account_id, role=x_role, email=x_user_email)


def require_internal(
    x_internal_token: str | None = Header(default=None),
    settings: Settings = Depends(settings_dep),
) -> None:
    if settings.internal_service_token and x_internal_token != settings.internal_service_token:
        raise CreditsError("forbidden", "Internal service token is invalid.", 403)


def require_account_scope(principal: Principal) -> str:
    if not principal.account_id:
        raise CreditsError("missing_account_scope", "Account-scoped credit routes require account_id.", 403)
    if principal.role not in ACCOUNT_ROLES:
        raise CreditsError("forbidden", "Role is not permitted for account credit routes.", 403)
    return principal.account_id


def require_owner(principal: Principal) -> str:
    account_id = require_account_scope(principal)
    if principal.role not in OWNER_ROLES:
        raise CreditsError("owner_required", "Owner role is required for marketplace operations.", 403)
    return account_id
