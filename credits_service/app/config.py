from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

SERVICE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILES = (str(SERVICE_ROOT / ".env"), str(PROJECT_ROOT / ".env"))


def credits_env(name: str) -> AliasChoices:
    return AliasChoices(f"CREDITS_{name}", name)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILES, env_file_encoding="utf-8", extra="ignore")

    app_name: str = Field(default="CreditFlow Credits / Marketplace Service", validation_alias=credits_env("APP_NAME"))
    environment: str = "local"
    log_level: str = "INFO"
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8080,http://127.0.0.1:8080"

    database_url: str = "postgresql://creditflow:creditflow@localhost:5432/creditflow"
    database_schema: str = Field(default="credits", validation_alias=credits_env("DATABASE_SCHEMA"))
    internal_service_token: str = Field(default="", validation_alias=AliasChoices("CREDITS_INTERNAL_SERVICE_TOKEN", "INTERNAL_SERVICE_TOKEN", "ADMIN_INTERNAL_SERVICE_TOKEN"), repr=False)

    rabbitmq_url: str = "amqp://guest:guest@localhost/"
    rabbitmq_exchange: str = "creditflow.events"
    rabbitmq_exchanges: str = Field(default="creditflow.events,billing_events", validation_alias=credits_env("RABBITMQ_EXCHANGES"))
    rabbitmq_queue: str = Field(default="creditflow.credits_service", validation_alias=credits_env("RABBITMQ_QUEUE"))

    billing_service_url: str = "http://localhost:8006"
    billing_service_timeout_seconds: float = Field(default=5.0, validation_alias=credits_env("BILLING_SERVICE_TIMEOUT_SECONDS"))

    low_balance_threshold: int = Field(default=500, validation_alias=credits_env("LOW_BALANCE_THRESHOLD"))
    default_currency: str = Field(default="usd", validation_alias=credits_env("DEFAULT_CURRENCY"))

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    @property
    def is_local(self) -> bool:
        return self.environment.lower() in {"local", "dev", "development", "test"}

    @property
    def exchanges(self) -> list[str]:
        values = [exchange.strip() for exchange in self.rabbitmq_exchanges.split(",") if exchange.strip()]
        if self.rabbitmq_exchange and self.rabbitmq_exchange not in values:
            values.insert(0, self.rabbitmq_exchange)
        return values


@lru_cache
def get_settings() -> Settings:
    return Settings()
