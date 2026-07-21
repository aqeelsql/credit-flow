import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.database import Database
from app.errors import CreditsError, register_error_handlers
from app.events import EventBus
from app.models import LedgerReason
from app.repository import CreditsRepository
from app.routers import credits, health

PLAN_CREDITS = {
    "starter": 4000,
    "pro": 25000,
    "scale": 90000,
}


def event_id_from_payload(routing_key: str, payload: dict[str, Any]) -> str:
    explicit_id = payload.get("event_id") or payload.get("id")
    if explicit_id:
        return str(explicit_id)
    if routing_key == "ai.generation_completed":
        if payload.get("request_id"):
            return str(payload["request_id"])
        if payload.get("job_id"):
            return f"ai.generation_completed:{payload['job_id']}"
    invoice_id = payload.get("invoice_id") or payload.get("payment_intent_id") or payload.get("refund_id")
    if invoice_id:
        return f"{routing_key}:{invoice_id}"
    account_id = payload.get("account_id", "unknown")
    timestamp = payload.get("created_at") or payload.get("timestamp") or "untimed"
    return f"{routing_key}:{account_id}:{timestamp}"


def credits_from_payload(payload: dict[str, Any]) -> int | None:
    for key in ("credits", "credits_delta", "credit_delta", "pack_credits"):
        value = payload.get(key)
        if value is not None:
            return abs(int(value))
    plan = payload.get("plan") or payload.get("plan_tier")
    if plan is not None:
        return PLAN_CREDITS.get(str(plan).lower())
    return None


def int_from_payload(payload: dict[str, Any], key: str) -> int | None:
    value = payload.get(key)
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def generation_credits_from_payload(payload: dict[str, Any]) -> int | None:
    total_tokens = int_from_payload(payload, "total_tokens")
    if total_tokens:
        return total_tokens
    prompt_tokens = int_from_payload(payload, "prompt_tokens") or 0
    completion_tokens = int_from_payload(payload, "completion_tokens") or 0
    if prompt_tokens + completion_tokens > 0:
        return prompt_tokens + completion_tokens
    text = f"{payload.get('prompt') or ''}\n{payload.get('response_text') or ''}".strip()
    if text:
        return max(1, (len(text) + 3) // 4)
    return None


def generation_metadata(payload: dict[str, Any], credits_used: int) -> dict[str, Any]:
    return {
        "kind": "ai_generation",
        "service": "ai_generation_service",
        "job_id": payload.get("job_id"),
        "request_id": payload.get("request_id"),
        "user_id": payload.get("user_id"),
        "model": payload.get("model"),
        "prompt_tokens": payload.get("prompt_tokens"),
        "completion_tokens": payload.get("completion_tokens"),
        "total_tokens": payload.get("total_tokens"),
        "credits_used": credits_used,
        "prompt_preview": str(payload.get("prompt") or "")[:240],
        "post_preview": str(payload.get("response_text") or "")[:320],
        "completed_at": payload.get("completed_at"),
    }


async def publish_or_log(event_bus: EventBus, routing_key: str, payload: dict[str, Any]) -> None:
    try:
        await event_bus.publish(routing_key, payload)
    except Exception as exc:
        logging.warning("Skipped publishing %s: %s", routing_key, exc)


async def publish_balance_events(
    repo: CreditsRepository,
    event_bus: EventBus,
    settings: Settings,
    account_id: str,
    delta: int,
    source_event_id: str,
    reason: str,
) -> None:
    balance = await repo.balance(account_id)
    await publish_or_log(
        event_bus,
        "credits.created" if delta > 0 else "credits.debited",
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


async def handle_service_event(
    settings: Settings,
    database: Database,
    event_bus: EventBus,
    routing_key: str,
    payload: dict[str, Any],
) -> None:
    account_id = payload.get("account_id")
    if not account_id:
        logging.warning("Skipped %s without account_id", routing_key)
        return

    credits = generation_credits_from_payload(payload) if routing_key == "ai.generation_completed" else credits_from_payload(payload)
    if not credits:
        logging.warning("Skipped %s without credits amount", routing_key)
        return

    event_id = event_id_from_payload(routing_key, payload)
    async with database.transaction() as conn:
        repo = CreditsRepository(conn)
        if routing_key == "invoice.paid":
            entry, applied = await repo.credit_account(str(account_id), credits, event_id, LedgerReason.PURCHASE, payload)
            if applied and entry:
                await publish_balance_events(repo, event_bus, settings, str(account_id), credits, event_id, "purchase")
            return

        if routing_key == "ai.generation_completed":
            metadata = generation_metadata(payload, credits)
            entry, applied = await repo.consume_credits(str(account_id), credits, event_id, metadata)
            if applied and entry:
                await publish_balance_events(repo, event_bus, settings, str(account_id), -credits, event_id, "ai_generation")
            return

        if routing_key == "refund.issued":
            entry, applied = await repo.debit_account(str(account_id), credits, event_id, LedgerReason.REFUND, payload)
            if applied and entry:
                await publish_balance_events(repo, event_bus, settings, str(account_id), -credits, event_id, "refund")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper())
    database = Database(settings)
    await database.connect()
    event_bus = EventBus(settings)
    app.state.database = database
    app.state.event_bus = event_bus

    async def event_handler(routing_key: str, payload: dict[str, Any]) -> None:
        await handle_service_event(settings, database, event_bus, routing_key, payload)

    event_bus.set_handler(event_handler)
    try:
        try:
            await event_bus.connect()
            await event_bus.start_consuming()
        except Exception as exc:
            logging.warning("RabbitMQ unavailable for credits events: %s", exc)
        yield
    finally:
        await event_bus.close()
        await database.close()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response

    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(credits.router)
    return app


app = create_app()
