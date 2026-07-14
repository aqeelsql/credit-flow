from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

SERVICE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILES = (str(SERVICE_ROOT / ".env"), str(PROJECT_ROOT / ".env"))


def user_tenant_env(name: str) -> AliasChoices:
    return AliasChoices(f"USER_TENANT_{name}", f"ACCOUNT_{name}", name)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILES, env_file_encoding="utf-8", extra="ignore")

    app_name: str = Field(default="CreditFlow User / Tenant Service", validation_alias=user_tenant_env("APP_NAME"))
    environment: str = "local"
    log_level: str = "INFO"
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8080,http://127.0.0.1:8080"

    database_url: str = "postgresql://creditflow:creditflow@localhost:5432/creditflow"
    database_schema: str = Field(default="user_tenant", validation_alias=user_tenant_env("DATABASE_SCHEMA"))
    internal_service_token: str = Field(default="", repr=False)

    invite_ttl_seconds: int = Field(default=7 * 24 * 60 * 60, validation_alias=user_tenant_env("INVITE_TTL_SECONDS"))
    default_plan: str = Field(default="Starter", validation_alias=user_tenant_env("DEFAULT_PLAN"))
    default_credits: int = Field(default=0, validation_alias=user_tenant_env("DEFAULT_CREDITS"))

    rabbitmq_url: str = "amqp://guest:guest@localhost/"
    rabbitmq_exchange: str = "creditflow.events"
    rabbitmq_queue: str = Field(default="creditflow.user_tenant_service", validation_alias=user_tenant_env("RABBITMQ_QUEUE"))

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

