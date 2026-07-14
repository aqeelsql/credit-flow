from fastapi import Depends, Header, Request

from app.config import Settings, get_settings
from app.database import Database
from app.errors import AccountError
from app.events import EventBus
from app.repository import AccountRepository
from app.schemas import Principal


MANAGER_ROLES = {"Owner", "TenantAdmin"}


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
        raise AccountError("missing_principal", "Gateway identity headers are required.", 401)
    return Principal(user_id=x_user_id, account_id=x_account_id, role=x_role, email=x_user_email)


def require_internal(
    x_internal_token: str | None = Header(default=None),
    settings: Settings = Depends(settings_dep),
) -> None:
    if settings.internal_service_token and x_internal_token != settings.internal_service_token:
        raise AccountError("forbidden", "Internal service token is invalid.", 403)


async def require_account_manager_membership(
    account_id: str,
    principal: Principal,
    db: Database,
    settings: Settings,
) -> None:
    if principal.account_id != account_id:
        raise AccountError("wrong_account_scope", "Request account does not match the active JWT account.", 403)
    async with db.acquire() as conn:
        repo = AccountRepository(conn, settings)
        membership = await repo.get_active_membership(account_id, principal.user_id)
    if not membership or membership["role"] not in MANAGER_ROLES:
        raise AccountError("manager_required", "Owner or TenantAdmin role is required for this account.", 403)
