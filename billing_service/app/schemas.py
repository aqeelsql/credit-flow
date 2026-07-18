from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Principal(BaseModel):
    user_id: str
    account_id: str | None = None
    role: str
    email: str | None = None


class CheckoutSessionRequest(BaseModel):
    plan: str = Field(pattern="^(free|starter|pro|team)$")


class CheckoutSessionResponse(BaseModel):
    checkout_url: str | None = None
    session_id: str | None = None
    plan: str
    status: str


class PaymentMethodSetupResponse(BaseModel):
    checkout_url: str
    session_id: str
    status: str


class SavedPaymentMethod(BaseModel):
    stripe_payment_method_id: str
    brand: str | None = None
    last4: str | None = None
    exp_month: int | None = None
    exp_year: int | None = None


class PaymentMethodResponse(BaseModel):
    status: str
    payment_method: SavedPaymentMethod | None = None


class InvoiceResponse(BaseModel):
    id: str
    stripe_invoice_id: str | None = None
    amount_paid: int
    amount_due: int
    currency: str
    status: str
    hosted_invoice_url: str | None = None
    invoice_pdf: str | None = None
    created_at: datetime


class InvoiceListResponse(BaseModel):
    items: list[InvoiceResponse]


class RefundRequest(BaseModel):
    invoice_id: str
    amount: int | None = Field(default=None, gt=0)
    reason: str | None = None


class RefundResponse(BaseModel):
    id: str
    status: str
    amount: int
    currency: str
    stripe_refund_id: str | None = None


class InternalCustomerRequest(BaseModel):
    account_id: str = Field(min_length=1, max_length=128)
    email: str | None = None
    name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class InternalCustomerResponse(BaseModel):
    account_id: str
    stripe_customer_id: str


class EscrowConfirmRequest(BaseModel):
    account_id: str
    listing_id: str
    payment_intent_id: str | None = None

