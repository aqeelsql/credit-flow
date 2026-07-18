from fastapi import APIRouter, Depends

from app.database import Database
from app.dependencies import database_dep

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    return {"status": "ok", "service": "notification"}


@router.get("/ready")
async def ready(db: Database = Depends(database_dep)):
    return {"status": "ready" if await db.ping() else "degraded"}
