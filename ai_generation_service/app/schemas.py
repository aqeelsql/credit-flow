from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class Principal(BaseModel):
    user_id: str
    account_id: str | None = None
    role: str
    email: str | None = None


class StartGenerationRequest(BaseModel):
    prompt: str = Field(min_length=1)
    account_id: str = Field(min_length=1, max_length=128)
    user_id: str = Field(min_length=1, max_length=128)
    request_id: str | None = Field(default=None, max_length=128)
    model: str | None = Field(default=None, max_length=255)

    @field_validator("prompt")
    @classmethod
    def prompt_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("prompt must not be blank")
        return value


class StartGenerationResponse(BaseModel):
    job_id: str
    channel: str
    status: str
    model: str


class GenerationJobResponse(BaseModel):
    id: str
    account_id: str
    user_id: str
    request_id: str | None = None
    channel: str
    model: str
    prompt: str
    response_text: str
    status: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    cost: Decimal | None = None
    error_reason: str | None = None
    cancellation_requested: bool
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class GenerationListResponse(BaseModel):
    items: list[GenerationJobResponse]


class CancellationResponse(BaseModel):
    job_id: str
    status: str


class StartImageGenerationRequest(BaseModel):
    account_id: str = Field(min_length=1, max_length=128)
    user_id: str = Field(min_length=1, max_length=128)
    source_text: str = Field(min_length=1)
    source_generation_job_id: str | None = None
    prompt: str | None = Field(default=None, max_length=4000)

    @field_validator("source_text")
    @classmethod
    def source_text_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("source_text must not be blank")
        return value


class ImageGenerationResponse(BaseModel):
    id: str
    account_id: str
    user_id: str
    source_generation_job_id: str | None = None
    provider: str
    model: str
    prompt: str
    source_text: str
    status: str
    image_url: str | None = None
    width: int | None = None
    height: int | None = None
    seed: int | None = None
    error_reason: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
