from fastapi import APIRouter, Depends

from app.database import Database
from app.dependencies import database_dep, redis_quota_dep
from app.redis_quota import RedisQuota

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    return {"status": "ok", "service": "usage"}


@router.get("/ready")
async def ready(db: Database = Depends(database_dep), redis_quota: RedisQuota = Depends(redis_quota_dep)):
    postgres_ok = await db.ping()
    redis_ok = await redis_quota.ping()
    return {"status": "ok" if postgres_ok and redis_ok else "degraded", "postgres": postgres_ok, "redis": redis_ok}

