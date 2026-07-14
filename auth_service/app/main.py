import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import Database
from app.errors import register_error_handlers
from app.events import EventPublisher
from app.redis_state import RedisState
from app.routers import auth, health


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    database = Database(settings)
    await database.connect()
    app.state.database = database
    app.state.redis_state = RedisState(settings)
    app.state.publisher = EventPublisher(settings)
    try:
        yield
    finally:
        await app.state.publisher.close()
        await app.state.redis_state.close()
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
    app.include_router(auth.router)
    return app


app = create_app()
