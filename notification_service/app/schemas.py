from datetime import datetime
from typing import Any

from pydantic import BaseModel


class NotificationLogItem(BaseModel):
    id: str
    event_id: str
    event_type: str
    notification_type: str
    channel: str
    recipient: str
    subject: str | None = None
    status: str
    provider: str
    provider_message_id: str | None = None
    attempt: int
    error: str | None = None
    metadata: dict[str, Any]
    created_at: datetime


class NotificationLogResponse(BaseModel):
    items: list[NotificationLogItem]
