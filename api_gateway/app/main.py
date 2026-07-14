import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.errors import register_error_handlers
from app.events import EventPublisher
from app.rate_limit import RateLimitMiddleware
from app.redis_state import RedisState
from app.routers import aggregate, health, images, proxy_routes, sse, webhooks


def create_app() -> FastAPI:
    settings = get_settings()
    redis_state = RedisState(settings)
    publisher = EventPublisher(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logging.basicConfig(level=settings.log_level.upper())
        # Connections are lazy so local development can start even when Redis or RabbitMQ is booting.
        yield
        await redis_state.close()
        await publisher.close()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
        responses={
            400: {"description": "Bad request"},
            401: {"description": "Unauthorized"},
            403: {"description": "Forbidden"},
            429: {"description": "Rate limited"},
            502: {"description": "Downstream unavailable"},
        },
    )
    app.state.settings = settings
    app.state.redis_state = redis_state
    app.state.publisher = publisher

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RateLimitMiddleware, settings=settings, redis_state=redis_state)

    register_error_handlers(app)

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response

    app.include_router(health.router)
    app.include_router(webhooks.router)
    app.include_router(sse.router)
    app.include_router(images.router)
    app.include_router(aggregate.router)
    app.include_router(proxy_routes.router)
    return app


app = create_app()
