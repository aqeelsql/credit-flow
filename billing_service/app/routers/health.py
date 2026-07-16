from fastapi import APIRouter, Depends

from app.database import Database
from app.dependencies import database_dep

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    return {"status": "ok", "service": "billing"}


@router.get("/ready")
async def ready(db: Database = Depends(database_dep)):
    postgres_ok = await db.ping()
    return {"status": "ok" if postgres_ok else "degraded", "postgres": postgres_ok}

