from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

SERVICE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILES = (str(SERVICE_ROOT / ".env"), str(PROJECT_ROOT / ".env"))


def scheduler_env(name: str) -> AliasChoices:
    return AliasChoices(f"SCHEDULER_{name}", name)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILES, env_file_encoding="utf-8", extra="ignore")

    app_name: str = Field(default="CreditFlow Scheduler Service", validation_alias=scheduler_env("APP_NAME"))
    environment: str = "local"
    log_level: str = "INFO"
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3005,http://127.0.0.1:3005"

    database_url: str = "postgresql://creditflow:creditflow@localhost:5432/creditflow"
    database_schema: str = Field(default="scheduler", validation_alias=scheduler_env("DATABASE_SCHEMA"))
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = Field(default="redis://localhost:6379/2", validation_alias=scheduler_env("CELERY_BROKER_URL"))
    celery_result_backend: str = Field(default="redis://localhost:6379/3", validation_alias=scheduler_env("CELERY_RESULT_BACKEND"))
    lock_redis_url: str = Field(default="redis://localhost:6379/4", validation_alias=scheduler_env("LOCK_REDIS_URL"))
    scan_interval_seconds: int = Field(default=60, validation_alias=scheduler_env("SCAN_INTERVAL_SECONDS"))
    due_batch_size: int = Field(default=100, validation_alias=scheduler_env("DUE_BATCH_SIZE"))

    rabbitmq_url: str = "amqp://guest:guest@localhost/"
    rabbitmq_exchange: str = "creditflow.events"
    internal_service_token: str = Field(default="", repr=False)

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
