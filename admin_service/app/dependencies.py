from fastapi import Header, Request

from app.database import Database
from app.errors import AdminError
from app.redis_sessions import RedisSessions
from app.schemas import Principal

ADMIN_ROLES = {"SuperAdmin", "TenantAdmin"}


def database_dep(request: Request) -> Database:
    return request.app.state.database


def redis_sessions_dep(request: Request) -> RedisSessions:
    return request.app.state.redis_sessions


async def current_principal(x_user_id: str | None = Header(default=None), x_account_id: str | None = Header(default=None), x_role: str | None = Header(default=None), x_user_email: str | None = Header(default=None)) -> Principal:
    if not x_user_id or not x_role:
        raise AdminError("missing_principal", "Gateway identity headers are required.", 401)
    if x_role not in ADMIN_ROLES:
        raise AdminError("forbidden", "SuperAdmin or TenantAdmin role is required.", 403)
    if x_role == "TenantAdmin" and not x_account_id:
        raise AdminError("missing_account_scope", "TenantAdmin routes require account_id.", 403)
    return Principal(user_id=x_user_id, account_id=x_account_id, role=x_role, email=x_user_email)


def scoped_account(principal: Principal, requested_account_id: str | None = None) -> str | None:
    if principal.role == "SuperAdmin":
        return requested_account_id
    if requested_account_id and requested_account_id != principal.account_id:
        raise AdminError("wrong_account_scope", "TenantAdmin can only access their own account.", 403)
    return principal.account_id
