from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class ScrapeRequested(BaseModel):
    event_id: str = Field(min_length=1, max_length=160)
    account_id: str | None = Field(default=None, max_length=128)
    requested_by_user_id: str | None = Field(default=None, max_length=128)
    target_url: str = Field(min_length=1, max_length=2048)
    job_type: str = Field(default="generic", max_length=64)
    metadata: dict = Field(default_factory=dict)

    @field_validator("target_url")
    @classmethod
    def target_must_be_http(cls, value: str) -> str:
        value = value.strip()
        if not value.startswith(("http://", "https://")):
            value = f"https://{value}"
        return value


class StartScrapeRequest(BaseModel):
    target_url: str = Field(min_length=1, max_length=2048)
    job_type: str = Field(default="generic", max_length=64)
    metadata: dict = Field(default_factory=dict)


class RecurringScrapeRequest(BaseModel):
    target_url: str = Field(min_length=1, max_length=2048)
    job_type: str = Field(default="competitor_check", max_length=64)
    interval_seconds: int = Field(default=86400, ge=60)
    metadata: dict = Field(default_factory=dict)


class TopicResearchRequest(BaseModel):
    topic: str = Field(min_length=3, max_length=500)
    job_type: str = Field(default="topic_research", max_length=64)
    output_type: str = Field(default="linkedin_post", max_length=64)
    max_sources: int = Field(default=5, ge=1, le=10)
    metadata: dict = Field(default_factory=dict)


class ResearchJobRequest(TopicResearchRequest):
    cadence: str = Field(default="once", pattern="^(once|daily|weekly|monthly)$")
    auto_generate_post: bool = False


class ScrapeDocumentResponse(BaseModel):
    id: str
    event_id: str | None = None
    target_url: str
    job_type: str
    status: str
    created_at: datetime | None = None
