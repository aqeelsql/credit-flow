from __future__ import annotations

from collections import Counter
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

    def superadmin_headers(self, principal: Principal | None = None) -> dict[str, str]:
        headers = {"x-user-id": principal.user_id if principal else "admin-service", "x-role": "SuperAdmin"}
        if principal and principal.email:
            headers["x-user-email"] = principal.email
        return headers

    def internal_headers(self) -> dict[str, str]:
        if not self.settings.internal_service_token:
            return {}
        return {"x-internal-token": self.settings.internal_service_token}

    async def _get(self, client: httpx.AsyncClient, url: str, headers: dict[str, str] | None = None, params: dict[str, Any] | None = None) -> tuple[dict[str, Any] | list[dict[str, Any]] | None, str | None]:
        try:
            response = await client.get(url, headers=headers, params=params)
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
            if err:
                errors["account"] = err
            members, err = await self._get(client, f"{self.settings.user_tenant_service_url.rstrip('/')}/{account_id}/team", headers)
            if err:
                errors["members"] = err
            credits, err = await self._get(client, f"{self.settings.credits_service_url.rstrip('/')}/balance", headers)
            if err:
                errors["credits"] = err
            usage, err = await self._get(client, f"{self.settings.usage_service_url.rstrip('/')}/usage/accounts/{account_id}/summary", headers)
            if err:
                errors["usage"] = err
        return {"account_id": account_id, "account": account if isinstance(account, dict) else None, "credits": credits if isinstance(credits, dict) else None, "usage": usage if isinstance(usage, dict) else None, "members": members if isinstance(members, list) else None, "errors": errors}

    async def list_accounts(self, *, q: str | None = None, limit: int = 100, offset: int = 0, principal: Principal | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if q:
            params["q"] = q
        async with httpx.AsyncClient(timeout=self.settings.downstream_timeout_seconds) as client:
            accounts, err = await self._get(client, f"{self.settings.user_tenant_service_url.rstrip('/')}/platform/accounts", headers=self.superadmin_headers(principal), params=params)
            if err and err.startswith("404:") and self.settings.internal_service_token:
                accounts, err = await self._get(client, f"{self.settings.user_tenant_service_url.rstrip('/')}/internal/accounts", self.internal_headers(), params=params)
        if err:
            return {"items": [], "errors": {"accounts": err}}
        if isinstance(accounts, list):
            return {"items": accounts, "errors": {}}
        if isinstance(accounts, dict):
            errors = accounts.get("errors")
            return {"items": accounts.get("items", []), "errors": errors if isinstance(errors, dict) else {}}
        return {"items": [], "errors": {"accounts": "Unexpected account directory response."}}

    async def platform_ops_summary(self, principal: Principal) -> dict[str, Any]:
        errors: dict[str, str] = {}
        account_count = 0
        total_credits_generated = 0
        package_count = 0
        active_package_credits = 0
        active_package_count = 0
        total_credits_sold = 0
        total_money_generated_cents = 0
        purchase_count = 0
        currency_counts: Counter[str] = Counter()

        async with httpx.AsyncClient(timeout=self.settings.downstream_timeout_seconds) as client:
            accounts, account_err = await self._get(
                client,
                f"{self.settings.user_tenant_service_url.rstrip('/')}/platform/accounts",
                headers=self.superadmin_headers(principal),
                params={"limit": 250, "offset": 0},
            )
            if account_err and account_err.startswith("404:") and self.settings.internal_service_token:
                accounts, account_err = await self._get(
                    client,
                    f"{self.settings.user_tenant_service_url.rstrip('/')}/internal/accounts",
                    headers=self.internal_headers(),
                    params={"limit": 250, "offset": 0},
                )
            if account_err:
                errors["accounts"] = account_err
            elif isinstance(accounts, dict):
                account_count = len(accounts.get("items") or [])
            elif isinstance(accounts, list):
                account_count = len(accounts)

            packages, package_err = await self._get(
                client,
                f"{self.settings.billing_service_url.rstrip('/')}/admin/credits/packages",
                headers=self.superadmin_headers(principal),
            )
            if package_err:
                errors["credit_packages"] = package_err
            elif isinstance(packages, list):
                package_count = len(packages)
                for package in packages:
                    try:
                        credits = int(package.get("credits") or 0)
                    except (TypeError, ValueError):
                        credits = 0
                    total_credits_generated += credits
                    if package.get("active", True):
                        active_package_count += 1
                        active_package_credits += credits
            else:
                errors["credit_packages"] = "Unexpected credit package response."

            purchases, purchase_err = await self._get(
                client,
                f"{self.settings.billing_service_url.rstrip('/')}/admin/credits/purchases",
                headers=self.superadmin_headers(principal),
            )
            if purchase_err:
                errors["credit_purchases"] = purchase_err
            elif isinstance(purchases, list):
                purchase_count = len(purchases)
                for purchase in purchases:
                    try:
                        total_credits_sold += int(purchase.get("credits") or 0)
                    except (TypeError, ValueError):
                        pass
                    try:
                        total_money_generated_cents += int(purchase.get("amount_paid") or 0)
                    except (TypeError, ValueError):
                        pass
                    currency = str(purchase.get("currency") or "usd").lower()
                    currency_counts[currency] += 1
            else:
                errors["credit_purchases"] = "Unexpected credit purchase response."

        return {
            "total_credits_generated": total_credits_generated,
            "package_count": package_count,
            "active_package_credits": active_package_credits,
            "active_package_count": active_package_count,
            "total_credits_sold": total_credits_sold,
            "credits_left": max(total_credits_generated - total_credits_sold, 0),
            "total_money_generated_cents": total_money_generated_cents,
            "currency": currency_counts.most_common(1)[0][0] if currency_counts else "usd",
            "purchase_count": purchase_count,
            "account_count": account_count,
            "errors": errors,
        }
