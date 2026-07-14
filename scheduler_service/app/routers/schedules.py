from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app.database import Database
from app.dependencies import Principal, current_principal, database_dep
from app.errors import SchedulerError
from app.repository import SchedulerRepository
from app.schemas import RescheduleRequest, ScheduleRequest, ScheduledPostListResponse, ScheduledPostResponse, to_utc

router = APIRouter(tags=["schedules"])


@router.get("/scheduled", response_model=ScheduledPostListResponse)
async def list_scheduled(start: datetime = Query(...), end: datetime = Query(...), timezone_name: str = Query(default="UTC", alias="timezone"), principal: Principal = Depends(current_principal), db: Database = Depends(database_dep)) -> ScheduledPostListResponse:
    start_utc = to_utc(start, timezone_name)
    end_utc = to_utc(end, timezone_name)
    async with db.acquire() as conn:
        items = await SchedulerRepository(conn).list_range(principal.account_id, start_utc, end_utc)
    return ScheduledPostListResponse(items=[ScheduledPostResponse.model_validate(item) for item in items])


@router.post("/scheduled", response_model=ScheduledPostResponse, status_code=201)
async def schedule_post(body: ScheduleRequest, principal: Principal = Depends(current_principal), db: Database = Depends(database_dep)) -> ScheduledPostResponse:
    publish_at_utc = to_utc(body.publish_at, body.timezone)
    async with db.transaction() as conn:
        item = await SchedulerRepository(conn).create(principal.account_id, principal.user_id, body.content_id, body.content_title or "Untitled content", publish_at_utc, body.timezone, body.recurrence)
    return ScheduledPostResponse.model_validate(item)


@router.get("/scheduled/{scheduled_post_id}", response_model=ScheduledPostResponse)
async def get_scheduled(scheduled_post_id: str, principal: Principal = Depends(current_principal), db: Database = Depends(database_dep)) -> ScheduledPostResponse:
    async with db.acquire() as conn:
        item = await SchedulerRepository(conn).get(scheduled_post_id, principal.account_id)
    if item is None:
        raise SchedulerError("scheduled_post_not_found", "Scheduled post was not found.", 404)
    return ScheduledPostResponse.model_validate(item)


@router.patch("/scheduled/{scheduled_post_id}", response_model=ScheduledPostResponse)
@router.post("/scheduled/{scheduled_post_id}/reschedule", response_model=ScheduledPostResponse)
async def reschedule_post(scheduled_post_id: str, body: RescheduleRequest, principal: Principal = Depends(current_principal), db: Database = Depends(database_dep)) -> ScheduledPostResponse:
    publish_at_utc = to_utc(body.publish_at, body.timezone)
    async with db.transaction() as conn:
        item = await SchedulerRepository(conn).reschedule(scheduled_post_id, principal.account_id, publish_at_utc, body.timezone, body.recurrence)
    return ScheduledPostResponse.model_validate(item)


@router.delete("/scheduled/{scheduled_post_id}", response_model=ScheduledPostResponse)
@router.post("/scheduled/{scheduled_post_id}/cancel", response_model=ScheduledPostResponse)
async def cancel_post(scheduled_post_id: str, principal: Principal = Depends(current_principal), db: Database = Depends(database_dep)) -> ScheduledPostResponse:
    async with db.transaction() as conn:
        item = await SchedulerRepository(conn).cancel(scheduled_post_id, principal.account_id)
    return ScheduledPostResponse.model_validate(item)
