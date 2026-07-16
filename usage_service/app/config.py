from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

SERVICE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILES = (str(SERVICE_ROOT / ".env"), str(PROJECT_ROOT / ".env"))


def usage_env(name: str) -> AliasChoices:
    return AliasChoices(f"USAGE_{name}", name)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILES, env_file_encoding="utf-8", extra="ignore", populate_by_name=True)

    app_name: str = Field(default="CreditFlow Usage / Metering Service", validation_alias=usage_env("APP_NAME"))
    environment: str = "local"
    log_level: str = "INFO"
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8080,http://127.0.0.1:8080"
    database_url: str = "postgresql://creditflow:creditflow@localhost:5432/creditflow"
    database_schema: str = Field(default="usage_metering", validation_alias=usage_env("DATABASE_SCHEMA"))
    redis_url: str = "redis://localhost:6379/0"
    redis_key_prefix: str = Field(default="usage", validation_alias=usage_env("REDIS_KEY_PREFIX"))
    redis_counter_ttl_seconds: int = Field(default=2678400, validation_alias=usage_env("REDIS_COUNTER_TTL_SECONDS"))
    reservation_ttl_seconds: int = Field(default=86400, validation_alias=usage_env("RESERVATION_TTL_SECONDS"))
    rabbitmq_url: str = "amqp://guest:guest@localhost/"
    rabbitmq_exchange: str = "creditflow.events"
    rabbitmq_queue: str = Field(default="creditflow.usage_service", validation_alias=usage_env("RABBITMQ_QUEUE"))
    retry_queue: str = Field(default="creditflow.usage_service.retry", validation_alias=usage_env("RETRY_QUEUE"))
    dlq_queue: str = Field(default="creditflow.usage_service.dlq", validation_alias=usage_env("DLQ_QUEUE"))
    retry_delay_ms: int = Field(default=30000, validation_alias=usage_env("RETRY_DELAY_MS"))
    max_retries: int = Field(default=3, validation_alias=usage_env("MAX_RETRIES"))
    internal_service_token: str = Field(default="", repr=False)
    default_monthly_token_quota: int = Field(default=100_000, validation_alias=usage_env("DEFAULT_MONTHLY_TOKEN_QUOTA"))
    default_currency: str = Field(default="usd", validation_alias=usage_env("DEFAULT_CURRENCY"))
    threshold_percentages: str = Field(default="80,100", validation_alias=usage_env("THRESHOLD_PERCENTAGES"))

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    @property
    def thresholds(self) -> list[int]:
        values: list[int] = []
        for raw in self.threshold_percentages.split(","):
            raw = raw.strip()
            if raw:
                values.append(int(raw))
        return sorted(set(values))


@lru_cache
def get_settings() -> Settings:
    return Settings()

