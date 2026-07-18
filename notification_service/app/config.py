from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

SERVICE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILES = (str(SERVICE_ROOT / ".env"), str(PROJECT_ROOT / ".env"))


def notification_env(name: str) -> AliasChoices:
    return AliasChoices(f"NOTIFICATION_{name}", name)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILES, env_file_encoding="utf-8", extra="ignore", populate_by_name=True)

    app_name: str = Field(default="CreditFlow Notification Service", validation_alias=notification_env("APP_NAME"))
    environment: str = "local"
    log_level: str = "INFO"
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    database_url: str = "postgresql://creditflow:creditflow@localhost:5432/creditflow"
    database_schema: str = Field(default="notifications", validation_alias=notification_env("DATABASE_SCHEMA"))

    rabbitmq_url: str = "amqp://guest:guest@localhost/"
    rabbitmq_exchanges: str = Field(default="creditflow.events,billing_events", validation_alias=notification_env("RABBITMQ_EXCHANGES"))
    publish_exchange: str = Field(default="creditflow.events", validation_alias=notification_env("PUBLISH_EXCHANGE"))
    retry_exchange: str = Field(default="notification.retry", validation_alias=notification_env("RETRY_EXCHANGE"))
    rabbitmq_queue: str = Field(default="creditflow.notification_service", validation_alias=notification_env("RABBITMQ_QUEUE"))
    retry_queue: str = Field(default="creditflow.notification_service.retry", validation_alias=notification_env("RETRY_QUEUE"))
    dlq_queue: str = Field(default="creditflow.notification_service.dlq", validation_alias=notification_env("DLQ_QUEUE"))
    retry_delay_ms: int = Field(default=30000, validation_alias=notification_env("RETRY_DELAY_MS"))
    max_retries: int = Field(default=3, validation_alias=notification_env("MAX_RETRIES"))

    resend_api_key: str = Field(default="", repr=False)
    resend_from_email: str = Field(default="CreditFlow <onboarding@resend.dev>", validation_alias=notification_env("RESEND_FROM_EMAIL"))
    resend_api_url: str = Field(default="https://api.resend.com/emails", validation_alias=notification_env("RESEND_API_URL"))
    frontend_base_url: str = Field(default="http://localhost:3000", validation_alias=notification_env("FRONTEND_BASE_URL"))
    support_email: str = Field(default="support@creditflow.local", validation_alias=notification_env("SUPPORT_EMAIL"))
    ops_email: str = Field(default="ops@creditflow.local", validation_alias=notification_env("OPS_EMAIL"))
    slack_webhook_url: str = Field(default="", repr=False, validation_alias=notification_env("SLACK_WEBHOOK_URL"))

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    @property
    def exchanges(self) -> list[str]:
        return [exchange.strip() for exchange in self.rabbitmq_exchanges.split(",") if exchange.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
