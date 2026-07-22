from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from app.config import Settings
from app.errors import BillingError
from app.repository import BillingRepository
from app.stripe_client import StripeClient


def _ts(value: Any):
    return datetime.fromtimestamp(int(value), UTC) if value else None


def _obj(data: Any) -> dict[str, Any]:
    return dict(data or {})


class BillingService:
    def __init__(self, settings: Settings, stripe_client: StripeClient):
        self.settings = settings
        self.stripe = stripe_client

    async def ensure_customer(self, repo: BillingRepository, account_id: str, email: str | None = None, name: str | None = None, metadata: dict | None = None) -> dict[str, Any]:
        existing = await repo.get_subscription(account_id)
        if existing and existing.get("stripe_customer_id"):
            return existing
        customer_id = await self.stripe.create_customer(account_id, email, name, metadata)
        return await repo.upsert_customer(account_id, customer_id, metadata=metadata)

    async def create_checkout_session(self, repo: BillingRepository, account_id: str, plan: str, email: str | None = None) -> dict[str, Any]:
        if plan == "free":
            sub = await repo.upsert_customer(account_id, (await self.ensure_customer(repo, account_id, email)).get("stripe_customer_id"), plan="free")
            await repo.add_outbox_event("subscription.updated", {"account_id": account_id, "plan": "free", "status": sub["status"]})
            return {"plan": plan, "status": "updated", "checkout_url": None, "session_id": None}
        price_value = self.settings.plan_prices.get(plan) or ""
        if not price_value:
            raise BillingError("plan_not_configured", f"Stripe price for {plan} is not configured.", 422)
        sub = await self.ensure_customer(repo, account_id, email)
        session = await self.stripe.create_checkout_session(customer_id=sub["stripe_customer_id"], account_id=account_id, plan=plan, price_value=price_value, credits=self.settings.plan_credits.get(plan, 0))
        return {"plan": plan, "status": "checkout_created", "checkout_url": session.url, "session_id": session.id}

    async def create_payment_method_setup_session(self, repo: BillingRepository, account_id: str, email: str | None = None) -> dict[str, Any]:
        sub = await self.ensure_customer(repo, account_id, email)
        session = await self.stripe.create_payment_method_setup_session(customer_id=sub["stripe_customer_id"], account_id=account_id)
        return {"status": "setup_created", "checkout_url": session.url, "session_id": session.id}

    async def create_credit_checkout_session(self, repo: BillingRepository, account_id: str, package_key: str, selected_credits: int, email: str | None = None) -> dict[str, Any]:
        package = await repo.get_active_credit_package(package_key)
        if package is None:
            raise BillingError("credit_package_not_found", "Credit package was not found.", 404)
        base_credits = int(package["credits"])
        base_price_cents = int(package["price_cents"])
        unit_price_cents = base_price_cents / base_credits
        checkout_price_cents = max(1, round(selected_credits * unit_price_cents))
        sub = await self.ensure_customer(repo, account_id, email, metadata={"credit_purchase_enabled": True})
        session = await self.stripe.create_credit_checkout_session(
            customer_id=sub["stripe_customer_id"],
            account_id=account_id,
            package_key=str(package["key"]),
            credits=selected_credits,
            price_cents=checkout_price_cents,
            currency=str(package.get("currency") or "usd"),
        )
        return {
            "status": "checkout_created",
            "checkout_url": session.url,
            "session_id": session.id,
            "package_key": str(package["key"]),
            "credits": selected_credits,
            "price_cents": checkout_price_cents,
            "currency": str(package.get("currency") or "usd"),
        }

    async def get_payment_method(self, repo: BillingRepository, account_id: str) -> dict[str, Any]:
        sub = await repo.get_subscription(account_id)
        if not sub or not sub.get("stripe_customer_id"):
            return {"status": "not_configured", "payment_method": None}
        payment_method = await self.stripe.get_default_payment_method(sub["stripe_customer_id"])
        return {"status": "configured" if payment_method else "not_configured", "payment_method": payment_method}

    async def process_credit_checkout_session(self, repo: BillingRepository, session: dict[str, Any], account_id: str | None = None) -> dict[str, Any]:
        metadata = _obj(session.get("metadata"))
        session_id = str(session.get("id") or "")
        session_account_id = str(metadata.get("account_id") or session.get("client_reference_id") or "")
        if not session_id:
            raise BillingError("invalid_checkout_session", "Stripe checkout session is missing an id.", 400)
        if not session_account_id:
            raise BillingError("missing_account_scope", "Stripe checkout session is missing account metadata.", 400)
        if account_id and account_id != session_account_id:
            raise BillingError("wrong_account_scope", "Checkout session does not belong to the active account.", 403)
        if metadata.get("purpose") != "credit_purchase":
            raise BillingError("invalid_checkout_purpose", "Checkout session is not a credit purchase.", 400)
        if str(session.get("payment_status") or "").lower() != "paid":
            raise BillingError("checkout_not_paid", "Stripe checkout is not paid yet.", 409)

        credits = int(metadata.get("credits") or 0)
        if credits <= 0:
            raise BillingError("missing_credits", "Credit checkout session does not include a credit amount.", 400)
        amount_paid = int(session.get("amount_total") or 0)
        currency = str(session.get("currency") or "usd")
        event_id = f"credit_purchase:{session_id}"
        invoice = await repo.upsert_credit_checkout_invoice(
            account_id=session_account_id,
            session=session,
            event_id=event_id,
            raw_event={"type": "checkout.session.completed", "data": {"object": session}},
        )
        outbox = await repo.add_outbox_event(
            "invoice.paid",
            {
                "event_id": event_id,
                "invoice_id": invoice["id"],
                "account_id": session_account_id,
                "amount_paid": amount_paid,
                "currency": currency,
                "credits_delta": credits,
                "package_key": metadata.get("package_key"),
                "stripe_checkout_session_id": session_id,
                "payment_intent_id": session.get("payment_intent"),
                "purpose": "credit_purchase",
            },
        )
        return {
            "status": "synced",
            "event_id": event_id,
            "invoice_id": invoice["id"],
            "outbox_event_id": outbox["id"],
            "account_id": session_account_id,
            "credits": credits,
            "amount_paid": amount_paid,
            "currency": currency,
            "package_key": metadata.get("package_key"),
        }

    async def sync_credit_checkout_session(self, repo: BillingRepository, session_id: str, account_id: str) -> dict[str, Any]:
        session = await self.stripe.retrieve_checkout_session(session_id)
        return await self.process_credit_checkout_session(repo, dict(session), account_id=account_id)

    async def grant_credit_purchase_direct(self, result: dict[str, Any]) -> dict[str, Any]:
        headers = {"accept": "application/json"}
        if self.settings.internal_service_token:
            headers["x-internal-token"] = self.settings.internal_service_token
        try:
            async with httpx.AsyncClient(timeout=self.settings.credits_service_timeout_seconds) as client:
                response = await client.post(
                    f"{self.settings.credits_service_url.rstrip('/')}/internal/credit",
                    headers=headers,
                    json={
                        "account_id": result["account_id"],
                        "amount": result["credits"],
                        "event_id": result["event_id"],
                        "reason": "purchase",
                        "metadata": {
                            "invoice_id": result["invoice_id"],
                            "amount_paid": result["amount_paid"],
                            "currency": result["currency"],
                            "package_key": result.get("package_key"),
                            "source": "billing_checkout_sync",
                        },
                    },
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as exc:
            raise BillingError("credits_grant_failed", f"Credits Service rejected the credit grant: {exc.response.status_code} {exc.response.text[:300]}", 502) from exc
        except httpx.RequestError as exc:
            raise BillingError("credits_service_unavailable", "Credits Service is unavailable; invoice was recorded but credits were not granted yet.", 503) from exc

    async def handle_stripe_event(self, repo: BillingRepository, event: dict[str, Any]) -> dict[str, Any]:
        event_id = str(event.get("id"))
        event_type = str(event.get("type"))
        obj = _obj(event.get("data", {}).get("object", {}))
        metadata = _obj(obj.get("metadata"))
        account_id = metadata.get("account_id") or obj.get("client_reference_id")
        is_new = await repo.record_webhook_event(event_id, event_type, str(account_id) if account_id else None, event)
        if not is_new:
            return {"status": "duplicate", "event_id": event_id}

        if event_type == "checkout.session.completed":
            account_id = str(account_id or obj.get("client_reference_id"))
            if metadata.get("purpose") == "save_payment_method" or obj.get("mode") == "setup":
                if obj.get("setup_intent"):
                    await self.stripe.set_default_payment_method_from_setup_intent(str(obj.get("setup_intent")))
                await repo.add_outbox_event("subscription.updated", {"event_id": event_id, "account_id": account_id, "status": "payment_method_saved", "stripe_customer_id": obj.get("customer")})
            elif metadata.get("purpose") == "credit_purchase":
                await self.process_credit_checkout_session(repo, obj, account_id=account_id)
            else:
                plan = str(metadata.get("plan") or "pro")
                await repo.update_subscription_state(account_id=account_id, customer_id=obj.get("customer"), subscription_id=obj.get("subscription"), plan=plan, status="active", metadata=metadata)
                await repo.add_outbox_event("subscription.updated", {"event_id": event_id, "account_id": account_id, "plan": plan, "stripe_customer_id": obj.get("customer"), "stripe_subscription_id": obj.get("subscription")})
        elif event_type in {"invoice.paid", "invoice.payment_succeeded"}:
            invoice = await repo.upsert_invoice(account_id=str(account_id) if account_id else None, invoice=obj, event_id=event_id, raw_event=event)
            await repo.add_outbox_event("invoice.paid", {"event_id": event_id, "invoice_id": invoice["id"], "account_id": invoice.get("account_id"), "amount_paid": invoice["amount_paid"], "currency": invoice["currency"], "credits": self.settings.plan_credits.get(str(metadata.get("plan") or "pro"), 0), "stripe_invoice_id": invoice.get("stripe_invoice_id")})
        elif event_type in {"invoice.payment_failed", "payment_intent.payment_failed"}:
            invoice = await repo.upsert_invoice(account_id=str(account_id) if account_id else None, invoice=obj, event_id=event_id, raw_event=event) if obj.get("object") == "invoice" else {}
            if account_id:
                await repo.mark_payment_failed(str(account_id), self.settings.dunning_grace_period_seconds)
            await repo.add_outbox_event("payment.failed", {"event_id": event_id, "account_id": str(account_id) if account_id else None, "invoice_id": invoice.get("id"), "reason": event_type})
        elif event_type == "setup_intent.succeeded":
            if obj.get("id"):
                await self.stripe.set_default_payment_method_from_setup_intent(str(obj.get("id")))
            if account_id:
                await repo.add_outbox_event("subscription.updated", {"event_id": event_id, "account_id": str(account_id), "status": "payment_method_saved"})
        elif event_type in {"customer.subscription.updated", "customer.subscription.deleted"}:
            account_id = str(account_id or metadata.get("account_id") or "")
            if account_id:
                await repo.update_subscription_state(account_id=account_id, customer_id=obj.get("customer"), subscription_id=obj.get("id"), plan=metadata.get("plan"), status=str(obj.get("status") or "updated"), period_end=_ts(obj.get("current_period_end")), metadata=metadata)
                await repo.add_outbox_event("subscription.updated", {"event_id": event_id, "account_id": account_id, "status": obj.get("status"), "plan": metadata.get("plan")})
        await repo.mark_webhook_processed(event_id)
        return {"status": "processed", "event_id": event_id, "event_type": event_type}

    async def process_dunning(self, repo: BillingRepository) -> list[dict[str, Any]]:
        rows = await repo.downgrade_expired_dunning()
        for row in rows:
            await repo.add_outbox_event("subscription.downgraded", {"account_id": row["account_id"], "plan": "free", "reason": "payment_failed_grace_period_expired"})
        return rows
