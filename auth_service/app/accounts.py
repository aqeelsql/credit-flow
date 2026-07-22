import httpx

from app.config import Settings
from app.errors import AuthError


def _headers(settings: Settings) -> dict[str, str]:
    headers = {"accept": "application/json"}
    if settings.internal_service_token:
        headers["x-internal-token"] = settings.internal_service_token
    return headers


async def _fetch_memberships(settings: Settings, user_id: str) -> list[dict]:
    if not settings.user_tenant_service_url:
        return []
    try:
        async with httpx.AsyncClient(timeout=settings.user_tenant_service_timeout_seconds) as client:
            response = await client.get(
                f"{settings.user_tenant_service_url.rstrip('/')}/internal/users/{user_id}/memberships",
                headers=_headers(settings),
            )
            response.raise_for_status()
            return response.json().get("memberships", [])
    except httpx.HTTPStatusError as exc:
        detail = ""
        try:
            body = exc.response.json()
            if isinstance(body, dict):
                raw = body.get("message") or body.get("detail") or body.get("error")
                if isinstance(raw, dict):
                    detail = str(raw.get("message") or raw.get("code") or raw)
                elif raw:
                    detail = str(raw)
        except ValueError:
            detail = exc.response.text[:300]
        suffix = f" User/Tenant returned {exc.response.status_code}: {detail}" if detail else f" User/Tenant returned {exc.response.status_code}."
        raise AuthError("account_lookup_failed", f"Account membership lookup failed.{suffix}", 502) from exc
    except httpx.RequestError as exc:
        raise AuthError("user_tenant_service_unavailable", "User / Tenant service is unavailable.", 503) from exc


async def create_individual_account(settings: Settings, user_id: str, email: str, account_name: str | None = None, name: str | None = None) -> dict:
    if not settings.user_tenant_service_url:
        return {"id": settings.default_account_id, "role": settings.default_role}
    try:
        async with httpx.AsyncClient(timeout=settings.user_tenant_service_timeout_seconds) as client:
            response = await client.post(
                f"{settings.user_tenant_service_url.rstrip('/')}/internal/users/{user_id}/individual-account",
                headers=_headers(settings),
                json={"email": email, "account_name": account_name, "name": name},
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        raise AuthError("account_bootstrap_failed", "Unable to create the signup account.", 502) from exc
    except httpx.RequestError as exc:
        raise AuthError("user_tenant_service_unavailable", "User / Tenant service is unavailable.", 503) from exc


async def validate_invite_for_email(settings: Settings, email: str, code: str) -> dict:
    if not settings.user_tenant_service_url:
        raise AuthError("user_tenant_service_unavailable", "User / Tenant service is unavailable.", 503)
    try:
        async with httpx.AsyncClient(timeout=settings.user_tenant_service_timeout_seconds) as client:
            response = await client.post(
                f"{settings.user_tenant_service_url.rstrip('/')}/internal/invites/validate",
                headers=_headers(settings),
                json={"email": email, "code": code},
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.json() if exc.response.headers.get("content-type", "").startswith("application/json") else {}
        message = detail.get("message") or "Invite code is invalid or does not match this email address."
        raise AuthError("invalid_invite", message, exc.response.status_code) from exc
    except httpx.RequestError as exc:
        raise AuthError("user_tenant_service_unavailable", "User / Tenant service is unavailable.", 503) from exc


async def accept_invite_for_user(settings: Settings, user_id: str, email: str, code: str, name: str | None = None) -> dict:
    if not settings.user_tenant_service_url:
        raise AuthError("user_tenant_service_unavailable", "User / Tenant service is unavailable.", 503)
    try:
        async with httpx.AsyncClient(timeout=settings.user_tenant_service_timeout_seconds) as client:
            response = await client.post(
                f"{settings.user_tenant_service_url.rstrip('/')}/internal/invites/accept",
                headers=_headers(settings),
                json={"user_id": user_id, "email": email, "code": code, "name": name},
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.json() if exc.response.headers.get("content-type", "").startswith("application/json") else {}
        message = detail.get("message") or "Unable to accept this invite."
        raise AuthError("invite_accept_failed", message, exc.response.status_code) from exc
    except httpx.RequestError as exc:
        raise AuthError("user_tenant_service_unavailable", "User / Tenant service is unavailable.", 503) from exc


async def resolve_account_role(settings: Settings, user_id: str, requested_account_id: str | None = None) -> tuple[str, str]:
    if not settings.user_tenant_service_url:
        return requested_account_id or settings.default_account_id, settings.default_role

    memberships = await _fetch_memberships(settings, user_id)
    if requested_account_id:
        for membership in memberships:
            if str(membership.get("account_id")) == requested_account_id and membership.get("status") == "active":
                return str(membership["account_id"]), str(membership.get("role") or "Member")
        raise AuthError("account_membership_missing", "User is not a member of the requested account.", 403)

    active_memberships = [membership for membership in memberships if membership.get("status") == "active"]
    if active_memberships:
        first = active_memberships[0]
        return str(first["account_id"]), str(first.get("role") or "Member")
    raise AuthError("account_membership_missing", "User does not belong to any active account.", 403)

