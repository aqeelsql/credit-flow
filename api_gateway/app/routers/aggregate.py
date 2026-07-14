import asyncio
from urllib.parse import urljoin

import httpx
from fastapi import APIRouter, Request

from app.auth import authenticate_request, enforce_roles, require_account
from app.proxy import build_forward_headers

router = APIRouter(prefix="/dashboard", tags=["aggregate"])


async def fetch_section(client: httpx.AsyncClient, base_url: str, path: str, headers: dict[str, str]) -> dict:
    target = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    try:
        response = await client.get(target, headers=headers)
        response.raise_for_status()
        return {"ok": True, "data": response.json()}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@router.get("/summary")
async def dashboard_summary(request: Request):
    settings = request.app.state.settings
    principal = await authenticate_request(request, settings, request.app.state.redis_state)
    enforce_roles(principal, {"Owner", "TenantAdmin", "Member"})
    require_account(principal)
    headers = build_forward_headers(request, principal)
    account_id = principal.account_id

    async with httpx.AsyncClient(timeout=settings.downstream_timeout_seconds) as client:
        account, credits, usage = await asyncio.gather(
            fetch_section(client, settings.user_tenant_service_url, f"{account_id}/summary", headers),
            fetch_section(client, settings.credits_service_url, f"credits/accounts/{account_id}/balance", headers),
            fetch_section(client, settings.usage_service_url, f"usage/accounts/{account_id}/summary", headers),
        )

    return {
        "account_id": account_id,
        "sections": {
            "account": account,
            "credits": credits,
            "usage": usage,
        },
    }


