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


class AccountDirectoryItem(BaseModel):
    id: str
    name: str
    type: str
    plan: str
    credits: int
    team_size: int
    owner_name: str | None = None
    owner_email: str | None = None
    created_at: str
    updated_at: str


class AccountDirectoryResponse(BaseModel):
    items: list[AccountDirectoryItem]
    errors: dict[str, str] = {}

class OpsSummaryResponse(BaseModel):
    total_credits_sold: int = 0
    total_money_generated_cents: int = 0
    currency: str = "usd"
    purchase_count: int = 0
    account_count: int = 0
    errors: dict[str, str] = {}

