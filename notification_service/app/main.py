import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.alerts import AlertClient
from app.config import get_settings
from app.database import Database
from app.email_client import EmailClient
from app.errors import register_error_handlers
from app.events import NotificationEventBus
from app.processor import NotificationProcessor
from app.routers import health, notifications


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper())
    database = Database(settings)
    event_bus = NotificationEventBus(settings)
    email_client = EmailClient(settings)
    alert_client = AlertClient(settings)
    processor = NotificationProcessor(settings, database, event_bus, email_client, alert_client)
    event_bus.set_handler(processor.handle_event)

    app.state.database = database
    app.state.event_bus = event_bus
    app.state.email_client = email_client
    await database.connect()
    await event_bus.start_consuming()
    try:
        yield
    finally:
        await event_bus.close()
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
    app.include_router(notifications.router)
    return app


app = create_app()
