from __future__ import annotations

import json

import stripe

from app.config import Settings
from app.errors import BillingError


class StripeClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        stripe.api_key = settings.stripe_secret_key

    def ensure_configured(self) -> None:
        if not self.settings.stripe_secret_key or not self.settings.stripe_secret_key.startswith("sk_test_"):
            raise BillingError("stripe_not_configured", "Stripe sandbox secret key is missing or not a test key.", 503)

    async def create_customer(self, account_id: str, email: str | None, name: str | None, metadata: dict | None = None) -> str:
        self.ensure_configured()
        customer = stripe.Customer.create(email=email, name=name, metadata={"account_id": account_id, **(metadata or {})})
        return str(customer.id)

    async def create_checkout_session(self, *, customer_id: str, account_id: str, plan: str, price_value: str, credits: int) -> stripe.checkout.Session:
        self.ensure_configured()
        params = {
            "mode": "subscription",
            "customer": customer_id,
            "success_url": self.settings.checkout_success_url or f"{self.settings.frontend_base_url}/billing?checkout=success",
            "cancel_url": self.settings.checkout_cancel_url or f"{self.settings.frontend_base_url}/billing?checkout=cancelled",
            "client_reference_id": account_id,
            "metadata": {"account_id": account_id, "plan": plan, "credits": str(credits)},
            "subscription_data": {"metadata": {"account_id": account_id, "plan": plan, "credits": str(credits)}},
        }
        if price_value.startswith("price_"):
            params["line_items"] = [{"price": price_value, "quantity": 1}]
        else:
            amount = int(float(price_value) * 100)
            params["line_items"] = [{"price_data": {"currency": "usd", "unit_amount": amount, "recurring": {"interval": "month"}, "product_data": {"name": f"CreditFlow {plan.title()}"}}, "quantity": 1}]
        return stripe.checkout.Session.create(**params)

    async def create_payment_method_setup_session(self, *, customer_id: str, account_id: str) -> stripe.checkout.Session:
        self.ensure_configured()
        return stripe.checkout.Session.create(
            mode="setup",
            customer=customer_id,
            payment_method_types=["card"],
            success_url=f"{self.settings.frontend_base_url}/billing?payment_method=success",
            cancel_url=f"{self.settings.frontend_base_url}/billing?payment_method=cancelled",
            client_reference_id=account_id,
            metadata={"account_id": account_id, "purpose": "save_payment_method"},
            setup_intent_data={"metadata": {"account_id": account_id, "purpose": "save_payment_method"}},
        )

    async def create_credit_checkout_session(self, *, customer_id: str, account_id: str, package_key: str, credits: int, price_cents: int, currency: str = "usd") -> stripe.checkout.Session:
        self.ensure_configured()
        metadata = {"account_id": account_id, "purpose": "credit_purchase", "package_key": package_key, "credits": str(credits)}
        return stripe.checkout.Session.create(
            mode="payment",
            customer=customer_id,
            success_url=f"{self.settings.frontend_base_url}/credits?checkout=success&type=credits&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{self.settings.frontend_base_url}/credits?checkout=cancelled",
            client_reference_id=account_id,
            metadata=metadata,
            payment_intent_data={"metadata": metadata},
            line_items=[
                {
                    "price_data": {
                        "currency": currency,
                        "unit_amount": price_cents,
                        "product_data": {"name": f"CreditFlow credits - {credits:,}"},
                    },
                    "quantity": 1,
                }
            ],
        )

    async def retrieve_checkout_session(self, session_id: str) -> stripe.checkout.Session:
        self.ensure_configured()
        return stripe.checkout.Session.retrieve(session_id)

    async def get_default_payment_method(self, customer_id: str) -> dict | None:
        self.ensure_configured()
        customer = stripe.Customer.retrieve(customer_id, expand=["invoice_settings.default_payment_method"])
        payment_method = customer.invoice_settings.default_payment_method
        if not payment_method:
            methods = stripe.PaymentMethod.list(customer=customer_id, type="card", limit=1)
            payment_method = methods.data[0] if methods.data else None
        if not payment_method:
            return None
        if isinstance(payment_method, str):
            payment_method = stripe.PaymentMethod.retrieve(payment_method)
        card = getattr(payment_method, "card", None)
        return {
            "stripe_payment_method_id": str(payment_method.id),
            "brand": getattr(card, "brand", None),
            "last4": getattr(card, "last4", None),
            "exp_month": getattr(card, "exp_month", None),
            "exp_year": getattr(card, "exp_year", None),
        }

    async def set_default_payment_method_from_setup_intent(self, setup_intent_id: str) -> None:
        self.ensure_configured()
        setup_intent = stripe.SetupIntent.retrieve(setup_intent_id)
        if setup_intent.customer and setup_intent.payment_method:
            stripe.Customer.modify(str(setup_intent.customer), invoice_settings={"default_payment_method": str(setup_intent.payment_method)})

    async def create_refund(self, payment_intent: str, amount: int | None, reason: str | None = None) -> stripe.Refund:
        self.ensure_configured()
        params = {"payment_intent": payment_intent}
        if amount:
            params["amount"] = amount
        if reason:
            params["metadata"] = {"reason": reason}
        return stripe.Refund.create(**params)

    def construct_event(self, payload: bytes, signature: str | None):
        if self.settings.stripe_webhook_secret and signature:
            return stripe.Webhook.construct_event(payload, signature, self.settings.stripe_webhook_secret)
        return stripe.Event.construct_from(json.loads(payload.decode("utf-8")), stripe.api_key)
