from fastapi import APIRouter, Depends, Request

from app.database import Database
from app.dependencies import database_dep

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    return {"status": "ok", "service": "admin"}


@router.get("/ready")
async def ready(request: Request, db: Database = Depends(database_dep)):
    redis_ok = await request.app.state.redis_sessions.ping()
    postgres_ok = await db.ping()
    return {"status": "ready" if redis_ok and postgres_ok else "degraded", "redis": redis_ok, "postgres": postgres_ok}
