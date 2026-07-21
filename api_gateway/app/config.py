from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SERVICE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILES = (str(SERVICE_ROOT / ".env"), str(PROJECT_ROOT / ".env"))


def gateway_env(name: str) -> AliasChoices:
    return AliasChoices(f"GATEWAY_{name}", name)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILES, env_file_encoding="utf-8", extra="ignore")

    app_name: str = Field(default="CreditFlow API Gateway", validation_alias=gateway_env("APP_NAME"))
    environment: str = "local"
    log_level: str = "INFO"

    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    jwt_algorithm: str = "HS256"
    jwt_secret: str = Field(default="dev-change-me", repr=False)
    jwt_public_key: str | None = None
    jwt_audience: str | None = None
    jwt_issuer: str | None = "creditflow-auth"

    redis_url: str = "redis://localhost:6379/0"
    rabbitmq_url: str = "amqp://guest:guest@localhost/"
    rabbitmq_exchange: str = "creditflow.events"
    internal_service_token: str = Field(default="", repr=False)
    webhook_ttl_seconds: int = Field(default=24 * 60 * 60, validation_alias=gateway_env("WEBHOOK_TTL_SECONDS"))

    rate_limit_window_seconds: int = Field(default=60, validation_alias=gateway_env("RATE_LIMIT_WINDOW_SECONDS"))
    rate_limit_account_requests: int = Field(default=600, validation_alias=gateway_env("RATE_LIMIT_ACCOUNT_REQUESTS"))
    rate_limit_ip_requests: int = Field(default=180, validation_alias=gateway_env("RATE_LIMIT_IP_REQUESTS"))
    rate_limit_fail_open: bool = Field(default=False, validation_alias=gateway_env("RATE_LIMIT_FAIL_OPEN"))

    auth_service_url: str = Field(default="http://localhost:8001", validation_alias=gateway_env("AUTH_SERVICE_URL"))
    user_tenant_service_url: str = Field(default="http://localhost:8002", validation_alias=AliasChoices("USER_TENANT_SERVICE_URL", "ACCOUNT_SERVICE_URL"))
    content_service_url: str = Field(default="http://localhost:8003", validation_alias=gateway_env("CONTENT_SERVICE_URL"))
    calendar_service_url: str = Field(default="http://localhost:8004", validation_alias=gateway_env("CALENDAR_SERVICE_URL"))
    linkedin_service_url: str = Field(default="http://localhost:8005", validation_alias=gateway_env("LINKEDIN_SERVICE_URL"))
    billing_service_url: str = Field(default="http://localhost:8006", validation_alias=gateway_env("BILLING_SERVICE_URL"))
    credits_service_url: str = Field(default="http://localhost:8007", validation_alias=gateway_env("CREDITS_SERVICE_URL"))
    admin_service_url: str = Field(default="http://localhost:8008", validation_alias=gateway_env("ADMIN_SERVICE_URL"))
    usage_service_url: str = "http://localhost:8009"
    ai_generation_service_url: str = Field(default="http://localhost:8010", validation_alias=gateway_env("AI_GENERATION_SERVICE_URL"))
    scraper_service_url: str = Field(default="http://localhost:8012", validation_alias=gateway_env("SCRAPER_SERVICE_URL"))

    downstream_timeout_seconds: float = Field(default=20.0, validation_alias=gateway_env("DOWNSTREAM_TIMEOUT_SECONDS"))
    sse_start_timeout_seconds: float = Field(default=15.0, validation_alias=gateway_env("SSE_START_TIMEOUT_SECONDS"))

    stripe_webhook_secret: str = Field(default="", repr=False, validation_alias=gateway_env("STRIPE_WEBHOOK_SECRET"))
    linkedin_webhook_secret: str = Field(default="", repr=False, validation_alias=gateway_env("LINKEDIN_WEBHOOK_SECRET"))
    openrouter_webhook_secret: str = Field(default="", repr=False, validation_alias=gateway_env("OPENROUTER_WEBHOOK_SECRET"))
    webhook_signature_tolerance_seconds: int = Field(default=300, validation_alias=gateway_env("WEBHOOK_SIGNATURE_TOLERANCE_SECONDS"))

    public_auth_paths: tuple[str, ...] = (
        "login",
        "signup",
        "refresh",
        "forgot-password/request",
        "forgot-password/reset",
        "verify-email",
    )

    @field_validator("jwt_algorithm", "jwt_issuer", "jwt_audience", mode="before")
    @classmethod
    def strip_jwt_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = str(value).strip()
        return stripped or None
    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    @property
    def service_urls(self) -> dict[str, str]:
        return {
            "auth": self.auth_service_url,
            "accounts": self.user_tenant_service_url,
            "content": self.content_service_url,
            "calendar": self.calendar_service_url,
            "linkedin": self.linkedin_service_url,
            "billing": self.billing_service_url,
            "credits": self.credits_service_url,
            "admin": self.admin_service_url,
            "usage": self.usage_service_url,
            "ai": self.ai_generation_service_url,
            "scraper": self.scraper_service_url,
        }

    @property
    def jwt_key(self) -> str:
        if self.jwt_algorithm.upper().startswith("RS") and self.jwt_public_key:
            return self.jwt_public_key.replace("\\n", "\n")
        return self.jwt_secret

    @property
    def jwt_algorithms(self) -> list[str]:
        return [algorithm.strip() for algorithm in self.jwt_algorithm.split(",") if algorithm.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()



