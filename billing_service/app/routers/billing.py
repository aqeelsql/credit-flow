from fastapi import APIRouter, Depends, Request

from app.config import Settings
from app.database import Database
from app.dependencies import current_principal, database_dep, require_internal, require_owner, require_superadmin, settings_dep
from app.errors import BillingError
from app.repository import BillingRepository
from app.schemas import CheckoutSessionRequest, CheckoutSessionResponse, CreateCreditPackageRequest, CreditCheckoutRequest, CreditCheckoutResponse, CreditCheckoutSyncResponse, CreditPackageResponse, CreditPurchaseResponse, EscrowConfirmRequest, InternalCustomerRequest, InternalCustomerResponse, InvoiceListResponse, PaymentMethodResponse, PaymentMethodSetupResponse, Principal, RefundRequest, RefundResponse, UpdateCreditPackageRequest
from app.service import BillingService
from app.stripe_client import StripeClient

router = APIRouter(tags=["billing"])


def service_dep(settings: Settings = Depends(settings_dep)) -> BillingService:
    return BillingService(settings, StripeClient(settings))


@router.post("/checkout/sessions", response_model=CheckoutSessionResponse)
async def create_checkout_session(payload: CheckoutSessionRequest, principal: Principal = Depends(current_principal), db: Database = Depends(database_dep), service: BillingService = Depends(service_dep)):
    account_id = require_owner(principal)
    async with db.transaction() as conn:
        result = await service.create_checkout_session(BillingRepository(conn), account_id, payload.plan, principal.email)
    return CheckoutSessionResponse(**result)


@router.get("/credits/packages", response_model=list[CreditPackageResponse])
async def list_credit_packages(db: Database = Depends(database_dep)):
    async with db.acquire() as conn:
        packages = await BillingRepository(conn).list_credit_packages(include_inactive=False)
    return [CreditPackageResponse(**package) for package in packages]


@router.get("/admin/credits/packages", response_model=list[CreditPackageResponse])
async def admin_list_credit_packages(principal: Principal = Depends(current_principal), db: Database = Depends(database_dep)):
    require_superadmin(principal)
    async with db.acquire() as conn:
        packages = await BillingRepository(conn).list_credit_packages(include_inactive=True)
    return [CreditPackageResponse(**package) for package in packages]


@router.get("/admin/credits/purchases", response_model=list[CreditPurchaseResponse])
async def admin_list_credit_purchases(account_id: str | None = None, principal: Principal = Depends(current_principal), db: Database = Depends(database_dep)):
    require_superadmin(principal)
    async with db.acquire() as conn:
        purchases = await BillingRepository(conn).list_credit_purchases(account_id=account_id, limit=100)
    return [CreditPurchaseResponse(**purchase) for purchase in purchases]


@router.post("/admin/credits/packages", response_model=CreditPackageResponse, status_code=201)
async def admin_create_credit_package(payload: CreateCreditPackageRequest, principal: Principal = Depends(current_principal), db: Database = Depends(database_dep)):
    user_id = require_superadmin(principal)
    async with db.transaction() as conn:
        package = await BillingRepository(conn).create_credit_package(key=payload.key, credits=payload.credits, price_cents=payload.price_cents, currency=payload.currency, created_by_user_id=user_id)
    return CreditPackageResponse(**package)


@router.patch("/admin/credits/packages/{package_id}", response_model=CreditPackageResponse)
async def admin_update_credit_package(package_id: str, payload: UpdateCreditPackageRequest, principal: Principal = Depends(current_principal), db: Database = Depends(database_dep)):
    require_superadmin(principal)
    async with db.transaction() as conn:
        package = await BillingRepository(conn).update_credit_package(package_id, credits=payload.credits, price_cents=payload.price_cents, currency=payload.currency, active=payload.active)
    return CreditPackageResponse(**package)


@router.delete("/admin/credits/packages/{package_id}", response_model=CreditPackageResponse)
async def admin_deactivate_credit_package(package_id: str, principal: Principal = Depends(current_principal), db: Database = Depends(database_dep)):
    require_superadmin(principal)
    async with db.transaction() as conn:
        package = await BillingRepository(conn).deactivate_credit_package(package_id)
    return CreditPackageResponse(**package)


@router.post("/checkout/credits", response_model=CreditCheckoutResponse)
async def create_credit_checkout(payload: CreditCheckoutRequest, principal: Principal = Depends(current_principal), db: Database = Depends(database_dep), service: BillingService = Depends(service_dep)):
    account_id = require_owner(principal)
    async with db.transaction() as conn:
        result = await service.create_credit_checkout_session(BillingRepository(conn), account_id, payload.package_key, payload.credits, principal.email)
    return CreditCheckoutResponse(**result)


@router.post("/checkout/credits/{session_id}/sync", response_model=CreditCheckoutSyncResponse)
async def sync_credit_checkout(session_id: str, principal: Principal = Depends(current_principal), db: Database = Depends(database_dep), service: BillingService = Depends(service_dep)):
    account_id = require_owner(principal)
    async with db.transaction() as conn:
        result = await service.sync_credit_checkout_session(BillingRepository(conn), session_id, account_id)
    await service.grant_credit_purchase_direct(result)
    return CreditCheckoutSyncResponse(**result)


@router.get("/billing/invoices", response_model=InvoiceListResponse)
async def invoice_history(principal: Principal = Depends(current_principal), db: Database = Depends(database_dep)):
    account_id = require_owner(principal)
    async with db.acquire() as conn:
        rows = await BillingRepository(conn).list_invoices(account_id)
    return InvoiceListResponse(items=rows)


@router.get("/billing/payment-method", response_model=PaymentMethodResponse)
async def payment_method(principal: Principal = Depends(current_principal), db: Database = Depends(database_dep), service: BillingService = Depends(service_dep)):
    account_id = require_owner(principal)
    async with db.acquire() as conn:
        result = await service.get_payment_method(BillingRepository(conn), account_id)
    return PaymentMethodResponse(**result)


@router.post("/billing/payment-method/setup", response_model=PaymentMethodSetupResponse)
async def setup_payment_method(principal: Principal = Depends(current_principal), db: Database = Depends(database_dep), service: BillingService = Depends(service_dep)):
    account_id = require_owner(principal)
    async with db.transaction() as conn:
        result = await service.create_payment_method_setup_session(BillingRepository(conn), account_id, principal.email)
    return PaymentMethodSetupResponse(**result)


@router.post("/billing/refunds", response_model=RefundResponse)
async def request_refund(payload: RefundRequest, principal: Principal = Depends(current_principal), db: Database = Depends(database_dep), service: BillingService = Depends(service_dep)):
    account_id = require_owner(principal)
    async with db.transaction() as conn:
        repo = BillingRepository(conn)
        invoice = await repo.get_invoice_by_id(payload.invoice_id, account_id)
        if not invoice:
            raise BillingError("invoice_not_found", "Invoice was not found.", 404)
        amount = payload.amount or int(invoice["amount_paid"] or invoice["amount_due"] or 0)
        refund = await repo.create_refund_record(account_id, payload.invoice_id, amount, invoice["currency"], payload.reason)
        payment_intent = (invoice.get("raw_event") or {}).get("data", {}).get("object", {}).get("payment_intent")
        stripe_refund_id = None
        if payment_intent:
            stripe_refund = await service.stripe.create_refund(str(payment_intent), amount, payload.reason)
            stripe_refund_id = str(stripe_refund.id)
        refund = await repo.mark_refund_issued(refund["id"], stripe_refund_id)
        await repo.add_outbox_event("refund.issued", {"refund_id": refund["id"], "account_id": account_id, "invoice_id": payload.invoice_id, "amount": amount, "currency": invoice["currency"], "stripe_refund_id": stripe_refund_id})
    return RefundResponse(**refund)


@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request, db: Database = Depends(database_dep), service: BillingService = Depends(service_dep)):
    body = await request.body()
    signature = request.headers.get("stripe-signature")
    try:
        event = service.stripe.construct_event(body, signature)
    except Exception as exc:
        raise BillingError("invalid_stripe_webhook", "Stripe webhook payload/signature is invalid.", 400) from exc
    async with db.transaction() as conn:
        return await service.handle_stripe_event(BillingRepository(conn), dict(event))


@router.post("/internal/customers", response_model=InternalCustomerResponse, dependencies=[Depends(require_internal)])
async def create_internal_customer(payload: InternalCustomerRequest, db: Database = Depends(database_dep), service: BillingService = Depends(service_dep)):
    async with db.transaction() as conn:
        row = await service.ensure_customer(BillingRepository(conn), payload.account_id, payload.email, payload.name, payload.metadata)
    return InternalCustomerResponse(account_id=payload.account_id, stripe_customer_id=row["stripe_customer_id"])


@router.post("/internal/marketplace/escrow/confirm", dependencies=[Depends(require_internal)])
async def confirm_marketplace_escrow(payload: EscrowConfirmRequest, db: Database = Depends(database_dep)):
    async with db.transaction() as conn:
        row = await BillingRepository(conn).confirm_marketplace_escrow(payload.account_id, payload.listing_id, payload.payment_intent_id)
    return {"status": "confirmed", **row}
