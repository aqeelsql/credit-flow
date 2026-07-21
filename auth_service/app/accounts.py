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
        raise AuthError("account_lookup_failed", "Account membership lookup failed.", 502) from exc
    except httpx.RequestError as exc:
        raise AuthError("user_tenant_service_unavailable", "User / Tenant service is unavailable.", 503) from exc


async def create_individual_account(settings: Settings, user_id: str, email: str, account_name: str | None = None) -> dict:
    if not settings.user_tenant_service_url:
        return {"id": settings.default_account_id, "role": settings.default_role}
    try:
        async with httpx.AsyncClient(timeout=settings.user_tenant_service_timeout_seconds) as client:
            response = await client.post(
                f"{settings.user_tenant_service_url.rstrip('/')}/internal/users/{user_id}/individual-account",
                headers=_headers(settings),
                json={"email": email, "account_name": account_name},
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        raise AuthError("account_bootstrap_failed", "Unable to create the signup account.", 502) from exc
    except httpx.RequestError as exc:
        raise AuthError("user_tenant_service_unavailable", "User / Tenant service is unavailable.", 503) from exc


async def accept_invite_for_user(settings: Settings, user_id: str, email: str, invite_code: str) -> dict:
    if not settings.user_tenant_service_url:
        raise AuthError("user_tenant_service_unavailable", "User / Tenant service is required for invite signup.", 503)
    try:
        async with httpx.AsyncClient(timeout=settings.user_tenant_service_timeout_seconds) as client:
            response = await client.post(
                f"{settings.user_tenant_service_url.rstrip('/')}/internal/invites/accept",
                headers=_headers(settings),
                json={"code": invite_code, "user_id": user_id, "email": email},
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        try:
            body = exc.response.json()
            detail = body.get("error", {}) if isinstance(body, dict) else {}
            message = detail.get("message") if isinstance(detail, dict) else None
            code = detail.get("code") if isinstance(detail, dict) else None
        except ValueError:
            message = None
            code = None
        raise AuthError(str(code or "invite_accept_failed"), str(message or "Invite code and email did not match."), exc.response.status_code) from exc
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

