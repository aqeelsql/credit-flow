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

    def internal_headers(self) -> dict[str, str]:
        if not self.settings.internal_service_token:
            return {}
        return {"x-internal-token": self.settings.internal_service_token}

    async def _get(self, client: httpx.AsyncClient, url: str, headers: dict[str, str] | None = None) -> tuple[dict[str, Any] | list[dict[str, Any]] | None, str | None]:
        try:
            response = await client.get(url, headers=headers, params=params)
            if response.status_code >= 400:
                return None, f"{response.status_code}: {response.text[:300]}"
            return response.json(), None
        except httpx.RequestError as exc:
            return None, str(exc)

    async def list_accounts(self, principal: Principal, q: str | None = None, limit: int = 100, offset: int = 0, enrich: bool = True) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if q:
            params["q"] = q
        headers = {"x-user-id": principal.user_id, "x-role": principal.role}
        if principal.email:
            headers["x-user-email"] = principal.email
        async with httpx.AsyncClient(timeout=self.settings.downstream_timeout_seconds) as client:
            accounts_payload, error = await self._get(client, f"{self.settings.user_tenant_service_url.rstrip('/')}/platform/accounts", headers=headers, params=params)
            if error and error.startswith("404:"):
                accounts_payload, fallback_error = await self._get(client, f"{self.settings.user_tenant_service_url.rstrip('/')}/", headers=headers, params=params)
                if not fallback_error and isinstance(accounts_payload, list):
                    normalized_accounts: list[dict[str, Any]] = []
                    for account in accounts_payload:
                        normalized_accounts.append(
                            {
                                "id": account.get("id"),
                                "name": account.get("name") or "Untitled account",
                                "type": account.get("type") or "individual",
                                "plan": account.get("plan") or "free",
                                "credits": int(account.get("credits") or 0),
                                "owner_user_id": account.get("owner_user_id"),
                                "owner_email": account.get("owner_email"),
                                "team_size": int(account.get("teamSize") or account.get("team_size") or 0),
                                "sync_errors": {
                                    "account_directory": "User/Tenant service is missing /platform/accounts; using scoped fallback data until it is restarted."
                                },
                            }
                        )
                    accounts_payload = normalized_accounts
                    error = None
                else:
                    error = f"{error}; fallback / failed: {fallback_error}"
            if error:
                from app.errors import AdminError
                raise AdminError("account_directory_failed", f"Account directory lookup failed: {error}", 502)
            accounts = accounts_payload if isinstance(accounts_payload, list) else []
            if not enrich:
                return accounts
            return await self._enrich_accounts(client, accounts, principal)

    async def _enrich_accounts(self, client: httpx.AsyncClient, accounts: list[dict[str, Any]], principal: Principal) -> list[dict[str, Any]]:
        enriched: list[dict[str, Any]] = []
        for account in accounts:
            account_id = str(account.get("id") or "")
            if not account_id:
                continue
            headers = self.headers(principal, account_id)
            credits, credits_error = await self._get(client, f"{self.settings.credits_service_url.rstrip('/')}/balance", headers=headers)
            usage, usage_error = await self._get(client, f"{self.settings.usage_service_url.rstrip('/')}/usage/accounts/{account_id}/summary", headers=headers)
            row = dict(account)
            if isinstance(credits, dict):
                row["credit_balance"] = credits.get("balance")
                row["low_balance_threshold"] = credits.get("low_balance_threshold")
                row["is_low_balance"] = credits.get("is_low_balance")
            if isinstance(usage, dict):
                row["tokens_used"] = usage.get("used_tokens")
                row["usage_cost"] = usage.get("total_cost")
                row["usage_period"] = usage.get("period")
                row["quota_tokens"] = usage.get("quota_tokens")
            errors: dict[str, str] = {}
            if credits_error:
                errors["credits"] = credits_error
            if usage_error:
                errors["usage"] = usage_error
            row["sync_errors"] = errors
            enriched.append(row)
        return enriched

    async def platform_overview(self, principal: Principal, q: str | None = None, limit: int = 100) -> dict[str, Any]:
        accounts = await self.list_accounts(principal, q=q, limit=limit, offset=0, enrich=True)
        total_credits = sum(int(account.get("credit_balance") or 0) for account in accounts)
        total_tokens = sum(int(account.get("tokens_used") or 0) for account in accounts)
        total_cost = sum(float(account.get("usage_cost") or 0) for account in accounts)
        total_members = sum(int(account.get("team_size") or 0) for account in accounts)
        accounts_with_errors = sum(1 for account in accounts if account.get("sync_errors"))
        async with httpx.AsyncClient(timeout=self.settings.downstream_timeout_seconds) as client:
            global_usage, global_usage_error = await self._get(client, f"{self.settings.usage_service_url.rstrip('/')}/admin/usage/summary")
        return {
            "accounts": accounts,
            "totals": {
                "accounts": len(accounts),
                "members": total_members,
                "credit_balance": total_credits,
                "tokens_used": total_tokens,
                "usage_cost": total_cost,
                "accounts_with_errors": accounts_with_errors,
            },
            "global_usage": global_usage if isinstance(global_usage, dict) else None,
            "errors": {"usage_global": global_usage_error} if global_usage_error else {},
        }

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

    async def list_accounts(self, *, q: str | None = None, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        params = []
        if q:
            params.append(("q", q))
        params.append(("limit", str(limit)))
        params.append(("offset", str(offset)))
        query = str(httpx.QueryParams(params))
        url = f"{self.settings.user_tenant_service_url.rstrip('/')}/internal/accounts?{query}"
        async with httpx.AsyncClient(timeout=self.settings.downstream_timeout_seconds) as client:
            accounts, err = await self._get(client, url, self.internal_headers())
        if err:
            return {"items": [], "errors": {"accounts": err}}
        if isinstance(accounts, dict):
            return {"items": accounts.get("items", []), "errors": {}}
        return {"items": [], "errors": {"accounts": "Unexpected account directory response."}}
