from datetime import datetime
from typing import Any
import json

import httpx
from fastapi import APIRouter, Depends, Query, status

from app.config import Settings
from app.database import Database
from app.dependencies import current_principal, database_dep, event_bus_dep, require_account_scope, require_internal, require_owner, settings_dep
from app.errors import CreditsError
from app.events import EventBus
from app.models import LedgerReason
from app.repository import CreditsRepository
from app.schemas import (
    BalanceResponse,
    BuyListingRequest,
    ConsumeCreditsRequest,
    CreateListingRequest,
    CreditAccountRequest,
    LedgerEntryResponse,
    MarketplaceListingResponse,
    Principal,
)

router = APIRouter(tags=["credits"])


def _json_dict(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def ledger_response(row: dict[str, Any]) -> LedgerEntryResponse:
    return LedgerEntryResponse(
        id=row["id"],
        account_id=row["account_id"],
        amount=row["amount"],
        reason=row["reason"],
        source_event_id=row.get("source_event_id"),
        related_account_id=row.get("related_account_id"),
        listing_id=row.get("listing_id"),
        metadata=_json_dict(row.get("metadata")),
        created_at=_iso(row["created_at"]) or "",
    )


def listing_response(row: dict[str, Any]) -> MarketplaceListingResponse:
    return MarketplaceListingResponse(
        id=row["id"],
        seller_account_id=row["seller_account_id"],
        credits=row["credits"],
        price_cents=row["price_cents"],
        currency=row["currency"],
        status=row["status"],
        buyer_account_id=row.get("buyer_account_id"),
        created_by_user_id=row.get("created_by_user_id"),
        created_at=_iso(row["created_at"]) or "",
        updated_at=_iso(row["updated_at"]) or "",
        sold_at=_iso(row.get("sold_at")),
    )


async def publish_or_log(event_bus: EventBus, routing_key: str, payload: dict[str, Any]) -> None:
    try:
        await event_bus.publish(routing_key, payload)
    except Exception:
        return


def ledger_reason_from_text(value: str, fallback: LedgerReason) -> LedgerReason:
    try:
        return LedgerReason(value)
    except ValueError:
        return fallback


async def publish_balance_events(
    repo: CreditsRepository,
    event_bus: EventBus,
    settings: Settings,
    account_id: str,
    delta: int,
    source_event_id: str | None,
    reason: str,
) -> None:
    balance = await repo.balance(account_id)
    routing_key = "credits.created" if delta > 0 else "credits.debited"
    await publish_or_log(
        event_bus,
        routing_key,
        {
            "account_id": account_id,
            "amount": abs(delta),
            "delta": delta,
            "balance": balance,
            "reason": reason,
            "source_event_id": source_event_id,
        },
    )
    await publish_or_log(
        event_bus,
        "credits.balance_changed",
        {
            "account_id": account_id,
            "delta": delta,
            "balance": balance,
            "reason": reason,
            "source_event_id": source_event_id,
        },
    )
    if balance <= settings.low_balance_threshold:
        await publish_or_log(
            event_bus,
            "credits.low_balance",
            {
                "account_id": account_id,
                "balance": balance,
                "threshold": settings.low_balance_threshold,
            },
        )


async def confirm_marketplace_payment(settings: Settings, listing: dict[str, Any], buyer_account_id: str, payment_intent_id: str | None) -> str:
    if settings.is_local:
        return payment_intent_id or f"local_pi_{listing['id']}_{buyer_account_id}"

    try:
        async with httpx.AsyncClient(timeout=settings.billing_service_timeout_seconds) as client:
            response = await client.post(
                f"{settings.billing_service_url.rstrip('/')}/internal/marketplace/escrow/confirm",
                json={
                    "listing_id": listing["id"],
                    "buyer_account_id": buyer_account_id,
                    "seller_account_id": listing["seller_account_id"],
                    "price_cents": listing["price_cents"],
                    "currency": listing["currency"],
                    "payment_intent_id": payment_intent_id,
                },
            )
            response.raise_for_status()
            payload = response.json()
            return str(payload.get("payment_intent_id") or payment_intent_id or payload.get("id"))
    except httpx.RequestError as exc:
        raise CreditsError("billing_service_unavailable", "Billing Service is unavailable for escrow confirmation.", 503) from exc
    except httpx.HTTPStatusError as exc:
        raise CreditsError("payment_not_confirmed", "Billing Service did not confirm marketplace payment.", 402) from exc


@router.get("/balance", response_model=BalanceResponse)
async def balance(
    principal: Principal = Depends(current_principal),
    settings: Settings = Depends(settings_dep),
    db: Database = Depends(database_dep),
) -> BalanceResponse:
    account_id = require_account_scope(principal)
    async with db.acquire() as conn:
        repo = CreditsRepository(conn)
        value = await repo.balance(account_id)
    return BalanceResponse(
        account_id=account_id,
        balance=value,
        low_balance_threshold=settings.low_balance_threshold,
        is_low_balance=value <= settings.low_balance_threshold,
    )


@router.get("/transactions", response_model=list[LedgerEntryResponse])
async def transactions(
    principal: Principal = Depends(current_principal),
    db: Database = Depends(database_dep),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[LedgerEntryResponse]:
    account_id = require_account_scope(principal)
    async with db.acquire() as conn:
        repo = CreditsRepository(conn)
        rows = await repo.list_transactions(account_id, limit)
    return [ledger_response(row) for row in rows]


@router.get("/marketplace/listings", response_model=list[MarketplaceListingResponse])
async def marketplace_listings(
    principal: Principal = Depends(current_principal),
    db: Database = Depends(database_dep),
    include_own: bool = Query(default=True),
) -> list[MarketplaceListingResponse]:
    account_id = require_account_scope(principal)
    async with db.acquire() as conn:
        repo = CreditsRepository(conn)
        rows = await repo.list_active_listings(account_id, include_own)
    return [listing_response(row) for row in rows]


@router.get("/marketplace/my-listings", response_model=list[MarketplaceListingResponse])
async def my_listings(
    principal: Principal = Depends(current_principal),
    db: Database = Depends(database_dep),
) -> list[MarketplaceListingResponse]:
    account_id = require_owner(principal)
    async with db.acquire() as conn:
        repo = CreditsRepository(conn)
        rows = await repo.list_account_listings(account_id)
    return [listing_response(row) for row in rows]


@router.post("/marketplace/listings", response_model=MarketplaceListingResponse, status_code=status.HTTP_201_CREATED)
async def create_listing(
    payload: CreateListingRequest,
    principal: Principal = Depends(current_principal),
    settings: Settings = Depends(settings_dep),
    db: Database = Depends(database_dep),
) -> MarketplaceListingResponse:
    account_id = require_owner(principal)
    async with db.transaction() as conn:
        repo = CreditsRepository(conn)
        row = await repo.create_listing(
            account_id,
            payload.credits,
            payload.price_cents,
            payload.currency or settings.default_currency,
            principal.user_id,
        )
    return listing_response(row)


@router.post("/marketplace/listings/{listing_id}/buy", response_model=MarketplaceListingResponse)
async def buy_listing(
    listing_id: str,
    payload: BuyListingRequest,
    principal: Principal = Depends(current_principal),
    settings: Settings = Depends(settings_dep),
    db: Database = Depends(database_dep),
    event_bus: EventBus = Depends(event_bus_dep),
) -> MarketplaceListingResponse:
    buyer_account_id = require_owner(principal)
    async with db.acquire() as conn:
        repo = CreditsRepository(conn)
        listing = await repo.get_listing(listing_id)
    if listing is None:
        raise CreditsError("listing_not_found", "Marketplace listing was not found.", 404)

    payment_intent_id = await confirm_marketplace_payment(settings, listing, buyer_account_id, payload.payment_intent_id)
    event_id = f"marketplace.purchase:{listing_id}:{payment_intent_id}"
    async with db.transaction() as conn:
        repo = CreditsRepository(conn)
        row = await repo.buy_listing(
            listing_id,
            buyer_account_id,
            event_id,
            {
                "payment_intent_id": payment_intent_id,
                "price_cents": listing["price_cents"],
                "currency": listing["currency"],
            },
        )
        await publish_balance_events(repo, event_bus, settings, row["seller_account_id"], -int(row["credits"]), event_id, "marketplace_sale")
        await publish_balance_events(repo, event_bus, settings, buyer_account_id, int(row["credits"]), event_id, "marketplace_purchase")
    return listing_response(row)


@router.post("/marketplace/listings/{listing_id}/cancel", response_model=MarketplaceListingResponse)
async def cancel_listing(
    listing_id: str,
    principal: Principal = Depends(current_principal),
    db: Database = Depends(database_dep),
) -> MarketplaceListingResponse:
    account_id = require_owner(principal)
    async with db.transaction() as conn:
        repo = CreditsRepository(conn)
        row = await repo.cancel_listing(listing_id, account_id)
    return listing_response(row)


@router.post("/consume", response_model=BalanceResponse)
async def consume_credits(
    payload: ConsumeCreditsRequest,
    principal: Principal = Depends(current_principal),
    settings: Settings = Depends(settings_dep),
    db: Database = Depends(database_dep),
    event_bus: EventBus = Depends(event_bus_dep),
) -> BalanceResponse:
    account_id = require_account_scope(principal)
    async with db.transaction() as conn:
        repo = CreditsRepository(conn)
        entry, applied = await repo.consume_credits(account_id, payload.amount, payload.event_id, payload.metadata)
        if applied and entry:
            await publish_balance_events(repo, event_bus, settings, account_id, -payload.amount, payload.event_id, payload.reason)
        balance_value = await repo.balance(account_id)
    return BalanceResponse(
        account_id=account_id,
        balance=balance_value,
        low_balance_threshold=settings.low_balance_threshold,
        is_low_balance=balance_value <= settings.low_balance_threshold,
    )


@router.post("/internal/credit", response_model=BalanceResponse, dependencies=[Depends(require_internal)])
async def internal_credit_account(
    payload: CreditAccountRequest,
    settings: Settings = Depends(settings_dep),
    db: Database = Depends(database_dep),
    event_bus: EventBus = Depends(event_bus_dep),
) -> BalanceResponse:
    async with db.transaction() as conn:
        repo = CreditsRepository(conn)
        reason = ledger_reason_from_text(payload.reason, LedgerReason.ADJUSTMENT)
        entry, applied = await repo.credit_account(payload.account_id, payload.amount, payload.event_id, reason, payload.metadata)
        if applied and entry:
            await publish_balance_events(repo, event_bus, settings, payload.account_id, payload.amount, payload.event_id, payload.reason)
        balance_value = await repo.balance(payload.account_id)
    return BalanceResponse(
        account_id=payload.account_id,
        balance=balance_value,
        low_balance_threshold=settings.low_balance_threshold,
        is_low_balance=balance_value <= settings.low_balance_threshold,
    )


@router.post("/internal/debit", response_model=BalanceResponse, dependencies=[Depends(require_internal)])
async def internal_debit_account(
    payload: CreditAccountRequest,
    settings: Settings = Depends(settings_dep),
    db: Database = Depends(database_dep),
    event_bus: EventBus = Depends(event_bus_dep),
) -> BalanceResponse:
    async with db.transaction() as conn:
        repo = CreditsRepository(conn)
        reason = ledger_reason_from_text(payload.reason, LedgerReason.ADJUSTMENT)
        entry, applied = await repo.debit_account(payload.account_id, payload.amount, payload.event_id, reason, payload.metadata)
        if applied and entry:
            await publish_balance_events(repo, event_bus, settings, payload.account_id, -payload.amount, payload.event_id, payload.reason)
        balance_value = await repo.balance(payload.account_id)
    return BalanceResponse(
        account_id=payload.account_id,
        balance=balance_value,
        low_balance_threshold=settings.low_balance_threshold,
        is_low_balance=balance_value <= settings.low_balance_threshold,
    )