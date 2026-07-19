from datetime import datetime
from typing import Any

from pydantic import BaseModel


class Principal(BaseModel):
    user_id: str
    account_id: str | None = None
    role: str
    email: str | None = None


class SessionResponse(BaseModel):
    jti: str
    user_id: str | None = None
    account_id: str | None = None
    role: str | None = None
    ttl_seconds: int | None = None


class RevokeSessionResponse(BaseModel):
    jti: str
    revoked: bool
    session: dict[str, Any] | None = None


class AuditLogItem(BaseModel):
    id: str
    event_id: str
    routing_key: str
    exchange: str | None = None
    account_id: str | None = None
    actor_user_id: str | None = None
    action: str
    summary: str | None = None
    payload: dict[str, Any]
    created_at: datetime


class AuditLogResponse(BaseModel):
    items: list[AuditLogItem]


class AccountOverviewResponse(BaseModel):
    account_id: str
    account: dict[str, Any] | None = None
    credits: dict[str, Any] | None = None
    usage: dict[str, Any] | None = None
    members: list[dict[str, Any]] | None = None
    errors: dict[str, str] = {}
