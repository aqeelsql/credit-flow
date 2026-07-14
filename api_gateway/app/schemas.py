from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str | None = None
    details: dict | list | str | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class Principal(BaseModel):
    user_id: str
    account_id: str | None = None
    role: str
    jti: str
    raw_claims: dict = Field(default_factory=dict)


class WebhookEnvelope(BaseModel):
    provider: str
    provider_event_id: str
    event_type: str
    account_id: str | None = None
    payload: dict


class AggregateSection(BaseModel):
    ok: bool
    data: dict | list | None = None
    error: str | None = None