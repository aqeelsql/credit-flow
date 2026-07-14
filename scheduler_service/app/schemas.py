from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator

from app.errors import SchedulerError

VALID_RECURRENCES = {"none", "daily", "weekly", "monthly"}


def to_utc(value: datetime, timezone_name: str) -> datetime:
    if value.tzinfo is None:
        try:
            value = value.replace(tzinfo=ZoneInfo(timezone_name))
        except ZoneInfoNotFoundError as exc:
            raise SchedulerError("invalid_timezone", "Timezone is invalid.", 422) from exc
    return value.astimezone(timezone.utc)


class ScheduleRequest(BaseModel):
    content_id: str = Field(min_length=1)
    content_title: str | None = Field(default=None, max_length=255)
    publish_at: datetime
    timezone: str = Field(default="UTC", max_length=128)
    recurrence: str = Field(default="none", max_length=24)

    @field_validator("recurrence")
    @classmethod
    def recurrence_is_supported(cls, value: str) -> str:
        value = value.lower()
        if value not in VALID_RECURRENCES:
            raise ValueError("recurrence must be 'none', 'daily', 'weekly', or 'monthly'")
        return value


class RescheduleRequest(BaseModel):
    publish_at: datetime
    timezone: str = Field(default="UTC", max_length=128)
    recurrence: str | None = Field(default=None, max_length=24)

    @field_validator("recurrence")
    @classmethod
    def recurrence_is_supported(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.lower()
        if value not in VALID_RECURRENCES:
            raise ValueError("recurrence must be 'none', 'daily', 'weekly', or 'monthly'")
        return value


class ScheduledPostResponse(BaseModel):
    id: str
    account_id: str
    created_by_user_id: str
    content_id: str
    content_title: str
    publish_at: datetime
    publish_at_local: str | None = None
    timezone: str
    recurrence: str
    status: str
    dispatch_attempts: int
    last_error: str | None = None
    locked_at: datetime | None = None
    dispatched_at: datetime | None = None
    cancelled_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ScheduledPostListResponse(BaseModel):
    items: list[ScheduledPostResponse]
