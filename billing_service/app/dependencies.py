from fastapi import Depends, Header, Request

from app.config import Settings, get_settings
from app.database import Database
from app.errors import BillingError
from app.schemas import Principal


def settings_dep() -> Settings:
    return get_settings()


def database_dep(request: Request) -> Database:
    return request.app.state.database


async def current_principal(x_user_id: str | None = Header(default=None), x_account_id: str | None = Header(default=None), x_role: str | None = Header(default=None), x_user_email: str | None = Header(default=None)) -> Principal:
    if not x_user_id or not x_role:
        raise BillingError("missing_principal", "Gateway identity headers are required.", 401)
    return Principal(user_id=x_user_id, account_id=x_account_id, role=x_role, email=x_user_email)


def require_owner(principal: Principal) -> str:
    if not principal.account_id:
        raise BillingError("missing_account_scope", "Billing routes require account_id.", 403)
    if principal.role != "Owner":
        raise BillingError("owner_required", "Owner role is required for billing operations.", 403)
    return principal.account_id


def require_superadmin(principal: Principal) -> str:
    if principal.role != "SuperAdmin":
        raise BillingError("superadmin_required", "SuperAdmin role is required.", 403)
    return principal.user_id


def require_internal(x_internal_token: str | None = Header(default=None), settings: Settings = Depends(settings_dep)) -> None:
    if settings.internal_service_token and x_internal_token != settings.internal_service_token:
        raise BillingError("forbidden", "Internal service token is invalid.", 403)

