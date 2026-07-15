import asyncio
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.crypto import TokenCipher
from app.database import Database
from app.errors import register_error_handlers
from app.events import SocialEventBus
from app.routers import health, linkedin
from app.token_refresh import refresh_tokens_forever
from app.worker import SocialWorker


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper())
    database = Database(settings)
    await database.connect()
    cipher = TokenCipher(settings)
    events = SocialEventBus(settings)
    worker = SocialWorker(database, events, cipher)
    events.handler = worker.handle
    app.state.settings = settings
    app.state.database = database
    app.state.events = events
    token_task = None
    try:
        try:
            await events.connect()
            await events.start_consuming()
        except Exception as exc:
            logging.warning("RabbitMQ unavailable for social publishing consumer: %s", exc)
        token_task = asyncio.create_task(refresh_tokens_forever(database, cipher))
        yield
    finally:
        if token_task:
            token_task.cancel()
        await events.close()
        await database.close()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response

    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(linkedin.router)
    return app


app = create_app()

