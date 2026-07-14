from fastapi import APIRouter, Depends, Request

from app.database import Database
from app.dependencies import database_dep

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "credits"}


@router.get("/ready")
async def ready(request: Request, db: Database = Depends(database_dep)) -> dict:
    postgres_ok = await db.ping()
    rabbitmq_ok = bool(getattr(request.app.state, "event_bus", None) and request.app.state.event_bus.connected)
    return {
        "status": "ready" if postgres_ok and rabbitmq_ok else "degraded",
        "checks": {"postgres": postgres_ok, "rabbitmq": rabbitmq_ok},
    }
