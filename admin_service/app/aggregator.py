from __future__ import annotations

from typing import Any

import httpx

from app.config import Settings
from app.schemas import Principal


class AggregatorClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def headers(self, principal: Principal, account_id: str) -> dict[str, str]:
        headers = {"x-user-id": principal.user_id, "x-role": principal.role, "x-account-id": account_id}
        if principal.email:
            headers["x-user-email"] = principal.email
        return headers

    async def _get(self, client: httpx.AsyncClient, url: str, headers: dict[str, str] | None = None) -> tuple[dict[str, Any] | list[dict[str, Any]] | None, str | None]:
        try:
            response = await client.get(url, headers=headers)
            if response.status_code >= 400:
                return None, f"{response.status_code}: {response.text[:300]}"
            return response.json(), None
        except httpx.RequestError as exc:
            return None, str(exc)

    async def account_overview(self, account_id: str, principal: Principal) -> dict[str, Any]:
        errors: dict[str, str] = {}
        headers = self.headers(principal, account_id)
        async with httpx.AsyncClient(timeout=self.settings.downstream_timeout_seconds) as client:
            account, err = await self._get(client, f"{self.settings.user_tenant_service_url.rstrip('/')}/{account_id}/summary", headers)
            if err: errors["account"] = err
            members, err = await self._get(client, f"{self.settings.user_tenant_service_url.rstrip('/')}/{account_id}/team", headers)
            if err: errors["members"] = err
            credits, err = await self._get(client, f"{self.settings.credits_service_url.rstrip('/')}/balance", headers)
            if err: errors["credits"] = err
            usage, err = await self._get(client, f"{self.settings.usage_service_url.rstrip('/')}/usage/accounts/{account_id}/summary", headers)
            if err: errors["usage"] = err
        return {"account_id": account_id, "account": account if isinstance(account, dict) else None, "credits": credits if isinstance(credits, dict) else None, "usage": usage if isinstance(usage, dict) else None, "members": members if isinstance(members, list) else None, "errors": errors}
