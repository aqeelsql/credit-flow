import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import Database
from app.dunning import DunningPoller
from app.errors import register_error_handlers
from app.events import BillingEventPublisher
from app.outbox import OutboxPoller
from app.routers import billing, health
from app.service import BillingService
from app.stripe_client import StripeClient


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper())
    database = Database(settings)
    publisher = BillingEventPublisher(settings)
    stripe_client = StripeClient(settings)
    service = BillingService(settings, stripe_client)
    outbox = OutboxPoller(database, publisher)
    dunning = DunningPoller(database, service)
    app.state.database = database
    app.state.publisher = publisher
    await database.connect()
    outbox.start()
    dunning.start()
    try:
        yield
    finally:
        await dunning.stop()
        await outbox.stop()
        await publisher.close()
        await database.close()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response

    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(billing.router)
    return app


app = create_app()

