from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from app.auth import current_principal, require_admin
from app.crypto import TokenCipher
from app.linkedin import LinkedInClient
from app.repository import SocialRepository
from app.state import create_state, verify_state

router = APIRouter(tags=["linkedin"])


async def _status(request: Request):
    principal = current_principal(request)
    async with request.app.state.database.acquire() as conn:
        connection = await SocialRepository(conn).get_connection(principal.account_id)
        jobs = await SocialRepository(conn).list_jobs(principal.account_id, 10)
    return {
        "connected": bool(connection),
        "connection": sanitize_connection(connection) if connection else None,
        "jobs": [dict(job) for job in jobs],
    }


def sanitize_connection(connection: dict | None) -> dict | None:
    if not connection:
        return None
    return {
        "id": connection["id"],
        "account_id": connection["account_id"],
        "provider": connection["provider"],
        "profile_name": connection.get("profile_name"),
        "email": connection.get("email"),
        "picture": connection.get("picture"),
        "scopes": connection.get("scopes") or [],
        "token_expires_at": connection.get("token_expires_at"),
        "status": connection.get("status"),
        "connected_at": connection.get("connected_at"),
        "refreshed_at": connection.get("refreshed_at"),
    }


@router.get("/status")
@router.get("/linkedin/status")
async def status(request: Request):
    return await _status(request)


@router.get("/connect")
@router.get("/linkedin/connect")
async def connect(request: Request):
    principal = current_principal(request)
    require_admin(principal)
    settings = request.app.state.settings
    state = create_state(settings, principal.account_id, principal.user_id)
    return {"auth_url": LinkedInClient(settings).authorization_url(state)}


@router.get("/callback")
@router.get("/linkedin/callback")
async def callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None, error_description: str | None = None):
    settings = request.app.state.settings
    if error:
        url = f"{settings.frontend_base_url.rstrip('/')}/linkedin?linkedin_error={error}"
        if error_description:
            url += f"&message={error_description}"
        return RedirectResponse(url)
    if not code or not state:
        return RedirectResponse(f"{settings.frontend_base_url.rstrip('/')}/linkedin?linkedin_error=missing_code_or_state")

    state_payload = verify_state(settings, state)
    linkedin = LinkedInClient(settings)
    token_data = await linkedin.exchange_code(code)
    access_token = token_data["access_token"]
    profile = await linkedin.userinfo(access_token)
    cipher = TokenCipher(settings)
    async with request.app.state.database.transaction() as conn:
        connection = await SocialRepository(conn).upsert_connection(
            account_id=state_payload["account_id"],
            user_id=state_payload["user_id"],
            profile=profile,
            encrypted_access_token=cipher.encrypt(access_token),
            encrypted_refresh_token=cipher.encrypt(token_data.get("refresh_token")) if token_data.get("refresh_token") else None,
            scopes=settings.scopes,
            expires_in=token_data.get("expires_in"),
            refresh_token_expires_in=token_data.get("refresh_token_expires_in"),
        )
    return RedirectResponse(f"{settings.frontend_base_url.rstrip('/')}/linkedin?connected=1&connection_id={connection['id']}")


@router.delete("/disconnect")
@router.delete("/linkedin/disconnect")
async def disconnect(request: Request):
    principal = current_principal(request)
    require_admin(principal)
    async with request.app.state.database.transaction() as conn:
        connection = await SocialRepository(conn).disconnect(principal.account_id)
    return {"disconnected": bool(connection)}


@router.get("/jobs")
@router.get("/linkedin/jobs")
async def jobs(request: Request, limit: int = 50):
    principal = current_principal(request)
    limit = min(max(limit, 1), 100)
    async with request.app.state.database.acquire() as conn:
        rows = await SocialRepository(conn).list_jobs(principal.account_id, limit)
    return {"items": [dict(row) for row in rows]}

