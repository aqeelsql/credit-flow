from dataclasses import dataclass

from fastapi import Header, Request

from app.errors import ScraperError


@dataclass
class Principal:
    user_id: str | None
    account_id: str | None
    role: str | None


def current_principal(request: Request) -> Principal:
    return Principal(user_id=request.headers.get("x-user-id"), account_id=request.headers.get("x-account-id"), role=request.headers.get("x-role"))


def require_internal(request: Request, x_internal_token: str = Header(default="")) -> None:
    expected = request.app.state.settings.internal_service_token
    if expected and x_internal_token != expected:
        raise ScraperError("forbidden", "Internal service token is invalid.", 403)


def repo_dep(request: Request):
    return request.app.state.repo


def events_dep(request: Request):
    return request.app.state.events
