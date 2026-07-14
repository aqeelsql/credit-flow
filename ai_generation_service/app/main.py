import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import Database
from app.errors import register_error_handlers
from app.events import EventPublisher
from app.generation import GenerationManager
from app.images import ImageGenerationManager
from app.redis_state import GenerationRedis
from app.routers import generations, health


def create_app() -> FastAPI:
    settings = get_settings()
    database = Database(settings)
    redis_state = GenerationRedis(settings)
    events = EventPublisher(settings)
    manager = GenerationManager(settings, database, redis_state, events)
    image_manager = ImageGenerationManager(settings, database, events)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logging.basicConfig(level=settings.log_level.upper())
        await database.connect()
        await redis_state.connect()
        try:
            yield
        finally:
            await manager.shutdown()
            await events.close()
            await redis_state.close()
            await database.close()

    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.database = database
    app.state.redis_state = redis_state
    app.state.events = events
    app.state.generation_manager = manager
    app.state.image_generation_manager = image_manager

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request.state.request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        response = await call_next(request)
        response.headers["x-request-id"] = request.state.request_id
        return response

    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(generations.router)
    return app


app = create_app()
