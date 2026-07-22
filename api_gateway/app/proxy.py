from urllib.parse import urljoin

import httpx
from fastapi import Request, Response

from app.auth import authenticate_request, enforce_roles, require_account
from app.config import Settings
from app.errors import GatewayError
from app.redis_state import RedisState
from app.schemas import Principal

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}

OWNER_ONLY = {
    ("accounts", "team"),
    ("billing", ""),
    ("credits", "marketplace/sell"),
}

MEMBER_ALLOWED_SERVICES = {"content", "calendar", "linkedin", "ai", "scraper"}
SUPERADMIN_ONLY_SERVICES: set[str] = set()
ADMIN_ALLOWED_SERVICES = {"admin"}


def _strip_path(path: str) -> str:
    return path.strip("/")


def is_public_auth_path(service_key: str, path: str, settings: Settings) -> bool:
    if service_key != "auth":
        return False
    clean_path = _strip_path(path)
    return clean_path in settings.public_auth_paths


def is_billing_admin_path(service_key: str, path: str) -> bool:
    return service_key == "billing" and _strip_path(path).startswith("admin/")


async def authenticate_for_proxy(request: Request, service_key: str, path: str, settings: Settings, redis_state: RedisState) -> Principal | None:
    if is_public_auth_path(service_key, path, settings):
        return None
    principal = await authenticate_request(request, settings, redis_state)
    if is_billing_admin_path(service_key, path):
        enforce_roles(principal, {"SuperAdmin"})
    elif service_key in SUPERADMIN_ONLY_SERVICES:
        enforce_roles(principal, {"SuperAdmin"})
    elif service_key in ADMIN_ALLOWED_SERVICES:
        enforce_roles(principal, {"SuperAdmin", "TenantAdmin"})
        if principal.role != "SuperAdmin":
            require_account(principal)
    elif service_key in MEMBER_ALLOWED_SERVICES:
        enforce_roles(principal, {"Owner", "TenantAdmin", "Member"})
        require_account(principal)
    else:
        require_account(principal)
        if service_key in {"billing", "credits"}:
            enforce_roles(principal, {"Owner"})
    return principal


def build_forward_headers(request: Request, principal: Principal | None) -> dict[str, str]:
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in HOP_BY_HOP_HEADERS
    }
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        headers["x-request-id"] = request_id
    if principal:
        headers["x-user-id"] = principal.user_id
        headers["x-role"] = principal.role
        headers["x-jti"] = principal.jti
        if principal.raw_claims.get("email"):
            headers["x-user-email"] = str(principal.raw_claims["email"])
        if principal.account_id:
            headers["x-account-id"] = principal.account_id
    return headers


def response_headers(headers: httpx.Headers) -> dict[str, str]:
    return {key: value for key, value in headers.items() if key.lower() not in HOP_BY_HOP_HEADERS}


async def proxy_request(request: Request, service_key: str, path: str, settings: Settings, redis_state: RedisState) -> Response:
    service_url = settings.service_urls.get(service_key)
    if not service_url:
        raise GatewayError("route_not_configured", f"No downstream service configured for {service_key}.", 502)

    principal = await authenticate_for_proxy(request, service_key, path, settings, redis_state)
    if service_key == "admin":
        admin_base_already_prefixed = service_url.rstrip("/").endswith("/admin")
        downstream_path = path if admin_base_already_prefixed else f"admin/{path.lstrip('/')}"
    else:
        downstream_path = path
    target = urljoin(service_url.rstrip("/") + "/", downstream_path.lstrip("/"))
    body = await request.body()
    headers = build_forward_headers(request, principal)

    try:
        async with httpx.AsyncClient(timeout=settings.downstream_timeout_seconds) as client:
            downstream = await client.request(
                request.method,
                target,
                params=request.query_params,
                content=body,
                headers=headers,
            )
    except httpx.RequestError as exc:
        raise GatewayError("downstream_unavailable", f"{service_key} service is unavailable.", 502) from exc

    return Response(
        content=downstream.content,
        status_code=downstream.status_code,
        headers=response_headers(downstream.headers),
        media_type=downstream.headers.get("content-type"),
    )

