from fastapi import Depends, Header

from app.config import Settings, get_settings
from app.errors import UsageError


def settings_dep() -> Settings:
    return get_settings()


async def require_internal(x_internal_token: str | None = Header(default=None), settings: Settings = Depends(settings_dep)) -> None:
    if settings.internal_service_token and x_internal_token != settings.internal_service_token:
        raise UsageError("unauthorized", "Invalid internal service token.", 401)

