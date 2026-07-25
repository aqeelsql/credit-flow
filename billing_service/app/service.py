from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
import logging

import httpx

from app.config import Settings
from app.errors import BillingError
from app.repository import BillingRepository
from app.stripe_client import StripeClient


def _ts(value: Any):
    return datetime.fromtimestamp(int(value), UTC) if value else None


def _obj(data: Any) -> dict[str, Any]:
    return dict(data or {})

def _to_plain_dict(data: Any) -> dict[str, Any]:
    if isinstance(data, dict):
        return data
    if hasattr(data, "to_dict_recursive"):
        return data.to_dict_recursive()
    if data:
        return dict(data)
    return {}


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
        sub = await self.ensure_customer(repo, account_id, email)
        current_plan = str(sub.get("plan") or "free")
        subscription_id = sub.get("stripe_subscription_id")
        if plan == current_plan and str(sub.get("status") or "").lower() in {"active", "trialing"}:
            return {"plan": plan, "status": "already_active", "checkout_url": None, "session_id": None}
        if plan == "free":
            if subscription_id:
                subscription = await self.stripe.schedule_subscription_cancel(subscription_id=str(subscription_id), account_id=account_id)
                await repo.update_subscription_state(account_id=account_id, customer_id=str(sub.get("stripe_customer_id") or ""), subscription_id=str(subscription_id), plan="free", status="cancel_at_period_end", period_end=_ts(getattr(subscription, "current_period_end", None)), metadata={"plan": "free", "downgrade_requested": True})
                await repo.add_outbox_event("subscription.updated", {"account_id": account_id, "plan": "free", "status": "cancel_at_period_end", "stripe_subscription_id": str(subscription_id)})
                return {"plan": plan, "status": "downgrade_scheduled", "checkout_url": None, "session_id": None}
            updated = await repo.upsert_customer(account_id, sub.get("stripe_customer_id"), plan="free", metadata={"plan": "free"})
            await repo.add_outbox_event("subscription.updated", {"account_id": account_id, "plan": "free", "status": updated["status"]})
            return {"plan": plan, "status": "updated", "checkout_url": None, "session_id": None}
        price_value = self.settings.plan_prices.get(plan) or ""
        if not price_value:
            raise BillingError("plan_not_configured", f"Stripe price for {plan} is not configured.", 422)
        credits = self.settings.plan_credits.get(plan, 0)
        session = await self.stripe.create_checkout_session(
            customer_id=sub["stripe_customer_id"],
            account_id=account_id,
            plan=plan,
            price_value=price_value,
            credits=credits,
            previous_subscription_id=str(subscription_id) if subscription_id and current_plan != "free" else None,
            previous_plan=current_plan if subscription_id and current_plan != "free" else None,
        )
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

    async def _enrich_session_invoice(self, session: dict[str, Any]) -> dict[str, Any]:
        invoice_ref = session.get("invoice")
        if invoice_ref and hasattr(invoice_ref, "to_dict_recursive"):
            return {**session, "invoice": invoice_ref.to_dict_recursive()}
        if invoice_ref and not isinstance(invoice_ref, dict):
            try:
                invoice = await self.stripe.retrieve_invoice(str(invoice_ref))
                session = {**session, "invoice": invoice.to_dict_recursive() if hasattr(invoice, "to_dict_recursive") else dict(invoice)}
            except Exception as exc:  # best-effort enrichment; the local invoice fallback still records the payment
                logging.warning("Unable to retrieve Stripe invoice %s for checkout %s: %s", invoice_ref, session.get("id"), exc)
        return session

    def _subscription_invoice_event_id(self, stripe_invoice_id: str | None) -> str:
        return f"subscription_invoice:{stripe_invoice_id}" if stripe_invoice_id else f"subscription_invoice:missing:{datetime.now(UTC).timestamp()}"

    def _plan_credit_payload(self, *, event_id: str, invoice: dict[str, Any], account_id: str, plan: str) -> dict[str, Any]:
        credits = int(self.settings.plan_credits.get(plan, 0))
        return {
            "event_id": event_id,
            "invoice_id": invoice.get("id"),
            "account_id": account_id,
            "amount_paid": int(invoice.get("amount_paid") or 0),
            "currency": str(invoice.get("currency") or "usd"),
            "credits_delta": credits,
            "credits": credits,
            "plan": plan,
            "stripe_invoice_id": invoice.get("stripe_invoice_id"),
            "purpose": "subscription_plan",
        }

    async def _subscription_from_stripe(self, subscription_id: str | None) -> dict[str, Any]:
        if not subscription_id:
            return {}
        try:
            return _to_plain_dict(await self.stripe.retrieve_subscription(subscription_id))
        except Exception as exc:
            logging.warning("Unable to retrieve Stripe subscription %s: %s", subscription_id, exc)
            return {}

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
        session = await self._enrich_session_invoice(session)
        amount_paid = int(session.get("amount_total") or 0)
        currency = str(session.get("currency") or "usd")
        event_id = f"credit_purchase:{session_id}"
        invoice = await repo.upsert_credit_checkout_invoice(
            account_id=session_account_id,
            session=session,
            event_id=event_id,
            raw_event={"type": "checkout.session.completed", "data": {"object": session}},
        )
        payment_intent_ref = session.get("payment_intent")
        if isinstance(payment_intent_ref, dict):
            payment_intent_id = payment_intent_ref.get("id")
        else:
            payment_intent_id = getattr(payment_intent_ref, "id", None) or payment_intent_ref
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
                "payment_intent_id": str(payment_intent_id) if payment_intent_id else None,
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
            "stripe_invoice_id": invoice.get("stripe_invoice_id"),
            "hosted_invoice_url": invoice.get("hosted_invoice_url"),
            "invoice_pdf": invoice.get("invoice_pdf"),
        }

    async def sync_credit_checkout_session(self, repo: BillingRepository, session_id: str, account_id: str) -> dict[str, Any]:
        session = await self.stripe.retrieve_checkout_session(session_id)
        return await self.process_credit_checkout_session(repo, dict(session), account_id=account_id)

    async def sync_subscription_checkout_session(self, repo: BillingRepository, session_id: str, account_id: str) -> dict[str, Any]:
        session = _to_plain_dict(await self.stripe.retrieve_checkout_session(session_id))
        metadata = _obj(session.get("metadata"))
        session_account_id = str(metadata.get("account_id") or session.get("client_reference_id") or "")
        if not session_account_id:
            raise BillingError("missing_account_scope", "Stripe checkout session is missing account metadata.", 400)
        if account_id != session_account_id:
            raise BillingError("wrong_account_scope", "Checkout session does not belong to the active account.", 403)
        if session.get("mode") != "subscription":
            raise BillingError("invalid_checkout_purpose", "Checkout session is not a subscription checkout.", 400)
        if str(session.get("status") or "").lower() != "complete":
            raise BillingError("checkout_not_complete", "Stripe checkout is not complete yet.", 409)

        plan = str(metadata.get("plan") or "pro")
        subscription_ref = session.get("subscription")
        subscription = subscription_ref if isinstance(subscription_ref, dict) else {}
        subscription_id = str(subscription.get("id") or subscription_ref or session.get("subscription") or "") or None
        invoice_ref = subscription.get("latest_invoice") or session.get("invoice")
        invoice = invoice_ref if isinstance(invoice_ref, dict) else {}
        if invoice_ref and not isinstance(invoice_ref, dict):
            try:
                invoice = _to_plain_dict(await self.stripe.retrieve_invoice(str(invoice_ref)))
            except Exception as exc:
                logging.warning("Unable to retrieve Stripe subscription invoice %s for checkout %s: %s", invoice_ref, session_id, exc)

        await repo.update_subscription_state(
            account_id=session_account_id,
            customer_id=str(session.get("customer")) if session.get("customer") else None,
            subscription_id=subscription_id,
            plan=plan,
            status=str(subscription.get("status") or "active"),
            period_end=_ts(subscription.get("current_period_end")),
            metadata=metadata,
        )
        local_invoice = None
        if invoice.get("id"):
            local_invoice = await repo.upsert_invoice(
                account_id=session_account_id,
                invoice=invoice,
                event_id=f"subscription_checkout:{session_id}",
                raw_event={"type": "checkout.session.completed", "data": {"object": session}},
            )
        subscription_event_id = f"subscription_checkout:{session_id}"
        if local_invoice:
            invoice_event_id = self._subscription_invoice_event_id(local_invoice.get("stripe_invoice_id"))
            await repo.add_outbox_event("invoice.paid", self._plan_credit_payload(event_id=invoice_event_id, invoice=local_invoice, account_id=session_account_id, plan=plan))
        previous_subscription_id = str(metadata.get("previous_subscription_id") or "")
        if previous_subscription_id and previous_subscription_id != str(subscription_id or ""):
            try:
                await self.stripe.cancel_subscription_now(subscription_id=previous_subscription_id)
            except Exception as exc:
                logging.warning("Unable to cancel previous Stripe subscription %s after checkout %s: %s", previous_subscription_id, session_id, exc)
        outbox = await repo.add_outbox_event(
            "subscription.updated",
            {"event_id": subscription_event_id, "account_id": session_account_id, "plan": plan, "status": "active", "stripe_customer_id": session.get("customer"), "stripe_subscription_id": subscription_id},
        )
        return {
            "status": "synced",
            "event_id": subscription_event_id,
            "account_id": session_account_id,
            "plan": plan,
            "credits": int(self.settings.plan_credits.get(plan, 0)),
            "amount_paid": int(local_invoice.get("amount_paid") or 0) if local_invoice else 0,
            "currency": str(local_invoice.get("currency") or "usd") if local_invoice else "usd",
            "stripe_subscription_id": subscription_id,
            "invoice_id": local_invoice.get("id") if local_invoice else None,
            "stripe_invoice_id": local_invoice.get("stripe_invoice_id") if local_invoice else None,
            "hosted_invoice_url": local_invoice.get("hosted_invoice_url") if local_invoice else None,
            "invoice_pdf": local_invoice.get("invoice_pdf") if local_invoice else None,
            "outbox_event_id": outbox.get("id"),
        }

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

    async def grant_subscription_plan_direct(self, result: dict[str, Any]) -> dict[str, Any] | None:
        credits = int(result.get("credits") or 0)
        invoice_id = result.get("invoice_id")
        if credits <= 0 or not invoice_id:
            return None
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
                        "amount": credits,
                        "event_id": self._subscription_invoice_event_id(result.get("stripe_invoice_id")),
                        "reason": "purchase",
                        "metadata": {
                            "invoice_id": invoice_id,
                            "stripe_invoice_id": result.get("stripe_invoice_id"),
                            "plan": result.get("plan"),
                            "amount_paid": result.get("amount_paid"),
                            "currency": result.get("currency"),
                            "source": "billing_subscription_checkout_sync",
                        },
                    },
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as exc:
            raise BillingError("credits_grant_failed", f"Credits Service rejected the subscription credit grant: {exc.response.status_code} {exc.response.text[:300]}", 502) from exc
        except httpx.RequestError as exc:
            raise BillingError("credits_service_unavailable", "Credits Service is unavailable; subscription invoice was recorded but plan credits were not granted yet.", 503) from exc

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
            subscription_ref = str(obj.get("subscription") or "")
            existing_subscription = await repo.find_subscription_for_stripe_refs(str(obj.get("customer") or ""), subscription_ref)
            if not account_id and existing_subscription:
                account_id = existing_subscription.get("account_id")
            stripe_subscription = await self._subscription_from_stripe(subscription_ref) if subscription_ref else {}
            subscription_metadata = _obj(stripe_subscription.get("metadata"))
            plan = str(metadata.get("plan") or subscription_metadata.get("plan") or (existing_subscription or {}).get("plan") or "pro")
            if account_id and stripe_subscription:
                await repo.update_subscription_state(
                    account_id=str(account_id),
                    customer_id=str(obj.get("customer")) if obj.get("customer") else None,
                    subscription_id=subscription_ref,
                    plan=plan,
                    status=str(stripe_subscription.get("status") or "active"),
                    period_end=_ts(stripe_subscription.get("current_period_end")),
                    metadata=subscription_metadata or metadata,
                )
            invoice = await repo.upsert_invoice(account_id=str(account_id) if account_id else None, invoice=obj, event_id=event_id, raw_event=event)
            if metadata.get("purpose") != "credit_purchase" and invoice.get("account_id"):
                invoice_event_id = self._subscription_invoice_event_id(invoice.get("stripe_invoice_id"))
                await repo.add_outbox_event("invoice.paid", self._plan_credit_payload(event_id=invoice_event_id, invoice=invoice, account_id=str(invoice["account_id"]), plan=plan))
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
