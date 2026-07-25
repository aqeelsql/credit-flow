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

    def _number(self, value: Any, default: int = 0) -> int:
        try:
            if value is None:
                return default
            return int(value)
        except (TypeError, ValueError):
            return default

    def _normalize_usage_for_account(self, usage: dict[str, Any] | None, credits: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(usage, dict):
            return usage
        normalized = dict(usage)
        used_tokens = self._number(
            normalized.get("used_tokens")
            or normalized.get("tokens_used")
            or normalized.get("total_tokens")
            or normalized.get("used")
            or normalized.get("usage")
        )
        credit_balance = self._number(
            credits.get("balance") if isinstance(credits, dict) else None,
            self._number(credits.get("credits") if isinstance(credits, dict) else None),
        )
        original_quota = self._number(
            normalized.get("quota_tokens")
            or normalized.get("quota")
            or normalized.get("monthly_quota")
            or normalized.get("limit")
        )
        account_credit_base = max(used_tokens + credit_balance, 0)
        usage_ratio = round((used_tokens / account_credit_base) * 100, 2) if account_credit_base > 0 else 0
        normalized["used_tokens"] = used_tokens
        normalized["quota_tokens"] = account_credit_base
        normalized["remaining_tokens"] = credit_balance
        normalized["credit_balance"] = credit_balance
        normalized["account_credit_base"] = account_credit_base
        normalized["usage_ratio_percent"] = usage_ratio
        if original_quota:
            normalized["monthly_quota_tokens"] = original_quota
        normalized["usage_basis"] = "credits_ledger"
        return normalized

    def _merge_account_billing(self, accounts: list[dict[str, Any]], subscriptions: list[dict[str, Any]] | None, invoices: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        by_account = {str(item.get("account_id")): item for item in subscriptions or [] if item.get("account_id")}
        invoice_stats: dict[str, dict[str, int]] = {}
        for invoice in invoices or []:
            account_id = str(invoice.get("account_id") or "")
            if not account_id:
                continue
            stats = invoice_stats.setdefault(account_id, {"invoice_count": 0, "subscription_revenue_cents": 0})
            stats["invoice_count"] += 1
            if invoice.get("stripe_subscription_id"):
                try:
                    stats["subscription_revenue_cents"] += int(invoice.get("amount_paid") or 0)
                except (TypeError, ValueError):
                    pass
        merged: list[dict[str, Any]] = []
        for account in accounts:
            item = dict(account)
            billing = by_account.get(str(account.get("id")))
            if billing:
                item["subscription_plan"] = billing.get("plan")
                item["subscription_status"] = billing.get("status")
                item["stripe_subscription_id"] = billing.get("stripe_subscription_id")
                item["plan"] = billing.get("plan") or item.get("plan")
            stats = invoice_stats.get(str(account.get("id")), {})
            item["invoice_count"] = int(stats.get("invoice_count") or 0)
            item["subscription_revenue_cents"] = int(stats.get("subscription_revenue_cents") or 0)
            merged.append(item)
        return merged

    async def _get(self, client: httpx.AsyncClient, url: str, headers: dict[str, str] | None = None, params: dict[str, Any] | None = None) -> tuple[dict[str, Any] | list[dict[str, Any]] | None, str | None]:
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
            invoices, err = await self._get(client, f"{self.settings.billing_service_url.rstrip('/')}/admin/invoices", self.superadmin_headers(principal), params={"account_id": account_id, "limit": 100})
            if err:
                errors["invoices"] = err
            subscriptions, err = await self._get(client, f"{self.settings.billing_service_url.rstrip('/')}/admin/subscriptions", self.superadmin_headers(principal), params={"account_id": account_id, "limit": 1})
            if err:
                errors["subscription"] = err
            elif isinstance(account, dict) and isinstance(subscriptions, list) and subscriptions:
                account = {**account, "plan": subscriptions[0].get("plan") or account.get("plan"), "subscription_plan": subscriptions[0].get("plan"), "subscription_status": subscriptions[0].get("status"), "stripe_subscription_id": subscriptions[0].get("stripe_subscription_id")}
        normalized_usage = self._normalize_usage_for_account(usage if isinstance(usage, dict) else None, credits if isinstance(credits, dict) else None)
        return {"account_id": account_id, "account": account if isinstance(account, dict) else None, "credits": credits if isinstance(credits, dict) else None, "usage": normalized_usage if isinstance(normalized_usage, dict) else None, "members": members if isinstance(members, list) else None, "invoices": invoices if isinstance(invoices, list) else None, "errors": errors}

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
        items = accounts if isinstance(accounts, list) else accounts.get("items", []) if isinstance(accounts, dict) else []
        errors = accounts.get("errors") if isinstance(accounts, dict) else {}
        async with httpx.AsyncClient(timeout=self.settings.downstream_timeout_seconds) as client:
            subscriptions, sub_err = await self._get(client, f"{self.settings.billing_service_url.rstrip('/')}/admin/subscriptions", headers=self.superadmin_headers(principal), params={"limit": limit, "offset": offset})
            invoices, inv_err = await self._get(client, f"{self.settings.billing_service_url.rstrip('/')}/admin/invoices", headers=self.superadmin_headers(principal), params={"limit": 250, "offset": 0})
        merged_errors = errors if isinstance(errors, dict) else {}
        if sub_err:
            merged_errors["subscriptions"] = sub_err
        if inv_err:
            merged_errors["invoices"] = inv_err
        return {"items": self._merge_account_billing(items, subscriptions if isinstance(subscriptions, list) else None, invoices if isinstance(invoices, list) else None), "errors": merged_errors}

    async def platform_ops_summary(self, principal: Principal) -> dict[str, Any]:
        errors: dict[str, str] = {}
        account_count = 0
        total_credits_generated = 0
        package_count = 0
        active_package_credits = 0
        active_package_count = 0
        total_credits_sold = 0
        total_money_generated_cents = 0
        subscription_revenue_cents = 0
        credit_purchase_revenue_cents = 0
        invoice_count = 0
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

            invoices, invoice_err = await self._get(
                client,
                f"{self.settings.billing_service_url.rstrip('/')}/admin/invoices",
                headers=self.superadmin_headers(principal),
            )
            if invoice_err:
                errors["invoices"] = invoice_err
            elif isinstance(invoices, list):
                invoice_count = len(invoices)
                for invoice in invoices:
                    try:
                        amount_paid = int(invoice.get("amount_paid") or 0)
                    except (TypeError, ValueError):
                        amount_paid = 0
                    total_money_generated_cents += amount_paid
                    if invoice.get("stripe_subscription_id"):
                        subscription_revenue_cents += amount_paid
                    elif amount_paid:
                        credit_purchase_revenue_cents += amount_paid
                    currency_counts[str(invoice.get("currency") or "usd").lower()] += 1
            else:
                errors["invoices"] = "Unexpected invoice response."

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
                    if errors.get("invoices"):
                        try:
                            purchase_amount = int(purchase.get("amount_paid") or 0)
                        except (TypeError, ValueError):
                            purchase_amount = 0
                        total_money_generated_cents += purchase_amount
                        credit_purchase_revenue_cents += purchase_amount
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
            "subscription_revenue_cents": subscription_revenue_cents,
            "credit_purchase_revenue_cents": credit_purchase_revenue_cents,
            "invoice_count": invoice_count,
            "currency": currency_counts.most_common(1)[0][0] if currency_counts else "usd",
            "purchase_count": purchase_count,
            "account_count": account_count,
            "errors": errors,
        }
