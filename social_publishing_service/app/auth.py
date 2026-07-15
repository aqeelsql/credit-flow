from dataclasses import dataclass

from fastapi import Request

from app.errors import SocialPublishingError


@dataclass
class Principal:
    user_id: str
    account_id: str
    role: str
    email: str | None = None


def current_principal(request: Request) -> Principal:
    user_id = request.headers.get("x-user-id")
    account_id = request.headers.get("x-account-id")
    role = request.headers.get("x-role")
    if not user_id or not account_id or not role:
        raise SocialPublishingError("missing_principal", "Gateway principal headers are required.", 401)
    return Principal(user_id=user_id, account_id=account_id, role=role, email=request.headers.get("x-user-email"))


def require_admin(principal: Principal) -> None:
    if principal.role not in {"Owner", "TenantAdmin"}:
        raise SocialPublishingError("forbidden", "Only Owner or TenantAdmin can manage LinkedIn connections.", 403)

