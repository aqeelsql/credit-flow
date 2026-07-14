from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

SERVICE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILES = (str(SERVICE_ROOT / ".env"), str(PROJECT_ROOT / ".env"))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = Field(default="CreditFlow AI Generation Service", validation_alias="AI_GENERATION_APP_NAME")
    environment: str = "local"
    log_level: str = "INFO"
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    database_url: str = "postgresql://creditflow:creditflow@localhost:5432/creditflow"
    database_schema: str = Field(default="ai_generation", validation_alias="AI_GENERATION_DATABASE_SCHEMA")
    redis_url: str = "redis://localhost:6379/0"
    rabbitmq_url: str = "amqp://guest:guest@localhost/"
    rabbitmq_exchange: str = "creditflow.events"
    internal_service_token: str = Field(default="", repr=False)

    usage_service_url: str = "http://localhost:8009"
    usage_service_timeout_seconds: float = Field(default=5.0, validation_alias="AI_GENERATION_USAGE_TIMEOUT_SECONDS")
    quota_backend: str = Field(default="redis", validation_alias="AI_GENERATION_QUOTA_BACKEND")
    daily_request_limit: int = Field(default=100, ge=1, validation_alias="AI_GENERATION_DAILY_REQUEST_LIMIT")

    openrouter_api_key: str = Field(default="", repr=False)
    openrouter_model: str = ""
    openrouter_fallback_model: str | None = "openrouter/free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_timeout_seconds: float = Field(default=120.0, validation_alias="AI_GENERATION_OPENROUTER_TIMEOUT_SECONDS")
    openrouter_site_url: str | None = None
    openrouter_app_name: str = "CreditFlow"

    max_prompt_characters: int = Field(default=20_000, validation_alias="AI_GENERATION_MAX_PROMPT_CHARACTERS")
    max_output_tokens: int = Field(default=2_048, validation_alias="AI_GENERATION_MAX_OUTPUT_TOKENS")
    stream_channel_prefix: str = "ai-generation"
    stream_event_ttl_seconds: int = Field(default=3600, validation_alias="AI_GENERATION_STREAM_EVENT_TTL_SECONDS")

    image_generation_provider: str = Field(default="pollinations", validation_alias="IMAGE_GENERATION_PROVIDER")
    pollinations_image_base_url: str = Field(default="https://image.pollinations.ai/prompt", validation_alias="POLLINATIONS_IMAGE_BASE_URL")
    pollinations_api_key: str = Field(default="", repr=False, validation_alias="POLLINATIONS_API_KEY")
    image_generation_model: str = Field(default="flux", validation_alias="IMAGE_GENERATION_MODEL")
    image_prompt_model: str | None = Field(default=None, validation_alias="IMAGE_PROMPT_MODEL")
    image_generation_timeout_seconds: float = Field(default=90.0, validation_alias="IMAGE_GENERATION_TIMEOUT_SECONDS")
    image_generation_width: int = Field(default=1024, validation_alias="IMAGE_GENERATION_WIDTH")
    image_generation_height: int = Field(default=1024, validation_alias="IMAGE_GENERATION_HEIGHT")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
