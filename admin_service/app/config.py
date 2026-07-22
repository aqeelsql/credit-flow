from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

SERVICE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILES = (str(SERVICE_ROOT / ".env"), str(PROJECT_ROOT / ".env"))


def admin_env(name: str) -> AliasChoices:
    return AliasChoices(f"ADMIN_{name}", name)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILES, env_file_encoding="utf-8", extra="ignore", populate_by_name=True)

    app_name: str = Field(default="CreditFlow Admin / Ops Service", validation_alias=admin_env("APP_NAME"))
    environment: str = "local"
    log_level: str = "INFO"
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    database_url: str = "postgresql://creditflow:creditflow@localhost:5432/creditflow"
    database_schema: str = Field(default="admin_ops", validation_alias=admin_env("DATABASE_SCHEMA"))
    user_tenant_database_schema: str = Field(default="user_tenant", validation_alias=AliasChoices("ADMIN_USER_TENANT_DATABASE_SCHEMA", "USER_TENANT_DATABASE_SCHEMA", "ACCOUNT_DATABASE_SCHEMA"))
    billing_database_schema: str = Field(default="billing", validation_alias=AliasChoices("ADMIN_BILLING_DATABASE_SCHEMA", "BILLING_DATABASE_SCHEMA"))
    redis_url: str = "redis://localhost:6379/0"
    revoked_session_ttl_seconds: int = Field(default=86400, validation_alias=admin_env("REVOKED_SESSION_TTL_SECONDS"))

    rabbitmq_url: str = "amqp://guest:guest@localhost/"
    rabbitmq_exchanges: str = Field(default="creditflow.events,billing_events", validation_alias=admin_env("RABBITMQ_EXCHANGES"))
    rabbitmq_queue: str = Field(default="creditflow.admin_ops.audit", validation_alias=admin_env("RABBITMQ_QUEUE"))

    credits_service_url: str = Field(default="http://localhost:8007", validation_alias=admin_env("CREDITS_SERVICE_URL"))
    usage_service_url: str = Field(default="http://localhost:8009", validation_alias=admin_env("USAGE_SERVICE_URL"))
    billing_service_url: str = Field(default="http://localhost:8006", validation_alias=admin_env("BILLING_SERVICE_URL"))
    user_tenant_service_url: str = Field(default="http://localhost:8002", validation_alias=AliasChoices("ADMIN_USER_TENANT_SERVICE_URL", "USER_TENANT_SERVICE_URL", "ACCOUNT_SERVICE_URL"))
    internal_service_token: str = Field(default="", validation_alias=AliasChoices("ADMIN_INTERNAL_SERVICE_TOKEN", "INTERNAL_SERVICE_TOKEN"), repr=False)
    downstream_timeout_seconds: float = Field(default=12.0, validation_alias=admin_env("DOWNSTREAM_TIMEOUT_SECONDS"))

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    @property
    def exchanges(self) -> list[str]:
        return [exchange.strip() for exchange in self.rabbitmq_exchanges.split(",") if exchange.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

