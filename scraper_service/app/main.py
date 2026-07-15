import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.errors import register_error_handlers
from app.events import ScraperEventBus
from app.mongodb import MongoState
from app.repository import ScraperRepository
from app.routers import health, scrapes
from app.scheduler import RecurringScrapeScheduler
from app.worker import ScrapeWorker


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper())
    mongo = MongoState(settings)
    await mongo.connect()
    repo = ScraperRepository(mongo, settings)
    events = ScraperEventBus(settings)
    worker = ScrapeWorker(settings, repo, events)
    events.handler = worker.handle
    scheduler = RecurringScrapeScheduler(repo, events, settings.recurring_scan_interval_seconds, settings)
    app.state.settings = settings
    app.state.mongo = mongo
    app.state.repo = repo
    app.state.events = events
    try:
        try:
            await events.connect()
            await events.start_consuming()
        except Exception as exc:
            logging.warning("RabbitMQ unavailable for scraper consumer: %s", exc)
        scheduler.start()
        yield
    finally:
        await scheduler.stop()
        await events.close()
        await mongo.close()


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
    app.include_router(scrapes.router)
    app.include_router(scrapes.router, prefix="/scraper")
    return app


app = create_app()
