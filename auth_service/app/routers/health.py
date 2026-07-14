from fastapi import APIRouter, Depends

from app.database import Database
from app.dependencies import database_dep, publisher_dep, redis_dep
from app.events import EventPublisher
from app.redis_state import RedisState

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "auth"}


@router.get("/ready")
async def ready(
    db: Database = Depends(database_dep),
    redis_state: RedisState = Depends(redis_dep),
    publisher: EventPublisher = Depends(publisher_dep),
) -> dict:
    checks = {
        "postgres": await db.ping(),
        "redis": await redis_state.ping(),
        "rabbitmq": await publisher.ready(),
    }
    status = "ready" if all(checks.values()) else "degraded"
    return {"status": status, "checks": checks}
