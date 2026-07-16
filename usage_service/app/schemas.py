from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class QuotaCheckRequest(BaseModel):
    account_id: str = Field(min_length=1, max_length=128)
    user_id: str | None = Field(default=None, max_length=128)
    operation: str = Field(default="text_generation", max_length=64)
    model: str = Field(min_length=1, max_length=255)
    max_tokens: int = Field(gt=0)
    request_id: str | None = Field(default=None, max_length=160)


class QuotaCheckResponse(BaseModel):
    allowed: bool
    account_id: str
    quota_tokens: int
    used_tokens: int
    reserved_tokens: int
    remaining_tokens: int
    period: str
    request_id: str | None = None
    reason: str | None = None


class AccountQuotaRequest(BaseModel):
    monthly_token_quota: int = Field(ge=0)
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class AccountQuotaResponse(BaseModel):
    account_id: str
    monthly_token_quota: int
    enabled: bool
    metadata: dict[str, Any]
    updated_at: datetime


class ModelUsageSummary(BaseModel):
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    total_cost: Decimal
    generations: int


class UsageSummaryResponse(BaseModel):
    account_id: str | None = None
    period: str | None = None
    quota_tokens: int | None = None
    used_tokens: int
    total_cost: Decimal
    remaining_tokens: int | None = None
    models: list[ModelUsageSummary]

