from fastapi import APIRouter, Depends, Query

from app.database import Database
from app.dependencies import database_dep
from app.repository import NotificationRepository
from app.schemas import NotificationLogResponse

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/logs", response_model=NotificationLogResponse)
async def list_notification_logs(limit: int = Query(default=50, ge=1, le=200), db: Database = Depends(database_dep)):
    async with db.acquire() as conn:
        rows = await NotificationRepository(conn).list_logs(limit)
    return NotificationLogResponse(items=rows)
