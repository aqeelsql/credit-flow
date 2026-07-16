import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import Database
from app.errors import register_error_handlers
from app.events import UsageEventBus
from app.processor import UsageProcessor
from app.redis_quota import RedisQuota
from app.routers import health, usage


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper())
    database = Database(settings)
    redis_quota = RedisQuota(settings)
    event_bus = UsageEventBus(settings)
    processor = UsageProcessor(settings, database, redis_quota, event_bus)
    app.state.database = database
    app.state.redis_quota = redis_quota
    app.state.event_bus = event_bus
    await database.connect()
    await redis_quota.connect()
    event_bus.set_handler(processor.handle)
    try:
        try:
            await event_bus.start_consuming()
        except Exception as exc:
            logging.warning("RabbitMQ unavailable for usage events: %s", exc)
        yield
    finally:
        await event_bus.close()
        await redis_quota.close()
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
    app.include_router(usage.router)
    return app


app = create_app()

