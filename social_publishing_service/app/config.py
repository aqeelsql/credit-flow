from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

SERVICE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILES = (str(SERVICE_ROOT / ".env"), str(PROJECT_ROOT / ".env"))


def social_env(name: str) -> AliasChoices:
    return AliasChoices(f"SOCIAL_PUBLISHING_{name}", name)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILES, env_file_encoding="utf-8", extra="ignore")

    app_name: str = Field(default="CreditFlow Social Publishing Service", validation_alias=social_env("APP_NAME"))
    environment: str = "local"
    log_level: str = "INFO"
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3005,http://127.0.0.1:3005"
    frontend_base_url: str = "http://localhost:3000"

    database_url: str = "postgresql://creditflow:creditflow@localhost:5432/creditflow"
    database_schema: str = Field(default="social_publishing", validation_alias=social_env("DATABASE_SCHEMA"))

    rabbitmq_url: str = "amqp://guest:guest@localhost/"
    rabbitmq_exchange: str = "creditflow.events"
    rabbitmq_queue: str = Field(default="creditflow.social_publishing_service", validation_alias=social_env("RABBITMQ_QUEUE"))
    retry_queue: str = Field(default="creditflow.social_publishing_service.retry", validation_alias=social_env("RETRY_QUEUE"))
    dlq_queue: str = Field(default="creditflow.social_publishing_service.dlq", validation_alias=social_env("DLQ_QUEUE"))
    max_retries: int = Field(default=3, validation_alias=social_env("MAX_RETRIES"))
    retry_delay_ms: int = Field(default=30000, validation_alias=social_env("RETRY_DELAY_MS"))

    content_service_url: str = Field(default="http://localhost:8003", validation_alias=social_env("CONTENT_SERVICE_URL"))
    content_upload_dir: str = Field(default=str(PROJECT_ROOT / "content_service" / "uploads"), validation_alias=social_env("CONTENT_UPLOAD_DIR"))
    internal_service_token: str = Field(default="", repr=False)

    token_encryption_key: str = Field(default="", repr=False, validation_alias=social_env("TOKEN_ENCRYPTION_KEY"))
    oauth_state_secret: str = Field(default="", repr=False, validation_alias=social_env("OAUTH_STATE_SECRET"))
    mock_mode: bool = Field(default=False, validation_alias=social_env("MOCK_MODE"))
    token_refresh_interval_seconds: int = Field(default=300, validation_alias=social_env("TOKEN_REFRESH_INTERVAL_SECONDS"))
    token_refresh_leeway_seconds: int = Field(default=900, validation_alias=social_env("TOKEN_REFRESH_LEEWAY_SECONDS"))

    linkedin_client_id: str = Field(default="", repr=False)
    linkedin_client_secret: str = Field(default="", repr=False)
    linkedin_redirect_uri: str = "http://localhost:8005/linkedin/callback"
    linkedin_scopes: str = "openid profile email w_member_social"
    linkedin_api_base_url: str = "https://api.linkedin.com"
    linkedin_auth_url: str = "https://www.linkedin.com/oauth/v2/authorization"
    linkedin_token_url: str = "https://www.linkedin.com/oauth/v2/accessToken"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    @property
    def scopes(self) -> list[str]:
        return [scope.strip() for scope in self.linkedin_scopes.split() if scope.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

