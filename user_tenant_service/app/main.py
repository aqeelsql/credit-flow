import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.database import Database
from app.errors import register_error_handlers
from app.events import EventBus
from app.repository import AccountRepository
from app.routers import accounts, health


async def handle_service_event(
    settings: Settings,
    database: Database,
    event_bus: EventBus,
    routing_key: str,
    payload: dict[str, Any],
) -> None:
    if routing_key == "user.registered":
        user_id = payload.get("user_id") or payload.get("sub")
        email = payload.get("email")
        if not user_id or not email:
            logging.warning("Skipped user.registered without user_id/email")
            return
        account_name = payload.get("account_name")
        async with database.transaction() as conn:
            repo = AccountRepository(conn, settings)
            row = await repo.ensure_individual_account(str(user_id), str(email), account_name)
        if row.get("_created"):
            await event_bus.publish(
                "account.created",
                {
                    "account_id": row["id"],
                    "user_id": str(user_id),
                    "name": row["name"],
                    "type": row["type"],
                    "plan": row["plan"],
                    "credits": row["credits"],
                    "team_size": row["team_size"],
                },
            )
        return

    if routing_key == "invoice.paid":
        account_id = payload.get("account_id")
        if not account_id:
            logging.warning("Skipped invoice.paid without account_id")
            return
        plan = payload.get("plan") or payload.get("plan_tier")
        credits_delta = payload.get("credits_delta") if "credits_delta" in payload else payload.get("credit_delta")
        credits = payload.get("credits")
        async with database.transaction() as conn:
            repo = AccountRepository(conn, settings)
            row = await repo.update_account_from_invoice(
                str(account_id),
                str(plan) if plan is not None else None,
                int(credits_delta) if credits_delta is not None else None,
                int(credits) if credits is not None else None,
            )
        if row is None:
            logging.warning("Skipped invoice.paid for unknown account %s", account_id)
            return
        await event_bus.publish(
            "account.updated",
            {
                "account_id": row["id"],
                "action": "invoice_paid",
                "plan": row["plan"],
                "credits": row["credits"],
                "team_size": row["team_size"],
            },
        )


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
            logging.warning("RabbitMQ unavailable for user/tenant events: %s", exc)
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
    app.include_router(accounts.router)
    return app


app = create_app()

