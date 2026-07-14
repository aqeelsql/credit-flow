from fastapi import Depends, Header, Request

from app.config import Settings, get_settings
from app.database import Database
from app.errors import GenerationError
from app.generation import GenerationManager
from app.images import ImageGenerationManager
from app.schemas import Principal

ACCOUNT_ROLES = {"Owner", "TenantAdmin", "Member"}


def settings_dep() -> Settings:
    return get_settings()


def database_dep(request: Request) -> Database:
    return request.app.state.database


def manager_dep(request: Request) -> GenerationManager:
    return request.app.state.generation_manager


def image_manager_dep(request: Request) -> ImageGenerationManager:
    return request.app.state.image_generation_manager


async def current_principal(
    x_user_id: str | None = Header(default=None),
    x_account_id: str | None = Header(default=None),
    x_role: str | None = Header(default=None),
    x_user_email: str | None = Header(default=None),
) -> Principal:
    if not x_user_id or not x_role:
        raise GenerationError("missing_principal", "Gateway identity headers are required.", 401)
    if not x_account_id:
        raise GenerationError("missing_account_scope", "AI generation routes require an account scope.", 403)
    if x_role not in ACCOUNT_ROLES:
        raise GenerationError("forbidden", "Role is not permitted for AI generation routes.", 403)
    return Principal(user_id=x_user_id, account_id=x_account_id, role=x_role, email=x_user_email)


def require_internal(
    x_internal_token: str | None = Header(default=None),
    settings: Settings = Depends(settings_dep),
) -> None:
    if settings.internal_service_token and x_internal_token != settings.internal_service_token:
        raise GenerationError("forbidden", "Internal service token is invalid.", 403)
