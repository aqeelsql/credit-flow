from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

SERVICE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILES = (str(SERVICE_ROOT / ".env"), str(PROJECT_ROOT / ".env"))


def auth_env(name: str) -> AliasChoices:
    return AliasChoices(f"AUTH_{name}", name)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILES, env_file_encoding="utf-8", extra="ignore")

    app_name: str = Field(default="CreditFlow Auth Service", validation_alias=auth_env("APP_NAME"))
    environment: str = "local"
    log_level: str = "INFO"
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8080,http://127.0.0.1:8080"

    database_url: str = "postgresql://creditflow:creditflow@localhost:5432/creditflow"
    database_schema: str = Field(default="auth", validation_alias=auth_env("DATABASE_SCHEMA"))
    redis_url: str = "redis://localhost:6379/0"
    rabbitmq_url: str = "amqp://guest:guest@localhost/"
    rabbitmq_exchange: str = "creditflow.events"

    bcrypt_rounds: int = Field(default=12, validation_alias=auth_env("BCRYPT_ROUNDS"))

    jwt_algorithm: str = "HS256"
    jwt_secret: str = Field(default="dev-change-me", repr=False)
    jwt_private_key: str | None = Field(default=None, repr=False, validation_alias=auth_env("JWT_PRIVATE_KEY"))
    jwt_public_key: str | None = None
    jwt_issuer: str = "creditflow-auth"
    jwt_audience: str | None = None
    access_token_ttl_seconds: int = Field(default=15 * 60, validation_alias=auth_env("ACCESS_TOKEN_TTL_SECONDS"))
    refresh_token_ttl_seconds: int = Field(default=30 * 24 * 60 * 60, validation_alias=auth_env("REFRESH_TOKEN_TTL_SECONDS"))

    email_verification_ttl_seconds: int = Field(default=24 * 60 * 60, validation_alias=auth_env("EMAIL_VERIFICATION_TTL_SECONDS"))
    frontend_base_url: str = Field(default="http://localhost:3000", validation_alias=auth_env("FRONTEND_BASE_URL"))
    password_reset_otp_ttl_seconds: int = Field(default=10 * 60, validation_alias=auth_env("PASSWORD_RESET_OTP_TTL_SECONDS"))
    password_reset_otp_length: int = Field(default=6, validation_alias=auth_env("PASSWORD_RESET_OTP_LENGTH"))

    login_rate_limit_window_seconds: int = Field(default=15 * 60, validation_alias=auth_env("LOGIN_RATE_LIMIT_WINDOW_SECONDS"))
    login_rate_limit_max_attempts: int = Field(default=8, validation_alias=auth_env("LOGIN_RATE_LIMIT_MAX_ATTEMPTS"))

    default_account_id: str = Field(default="acct_individual_pending", validation_alias=auth_env("DEFAULT_ACCOUNT_ID"))
    default_role: str = Field(default="Owner", validation_alias=auth_env("DEFAULT_ROLE"))
    user_tenant_service_url: str | None = Field(default="http://localhost:8002", validation_alias=AliasChoices("USER_TENANT_SERVICE_URL", "ACCOUNT_SERVICE_URL"))
    user_tenant_service_timeout_seconds: float = Field(default=5.0, validation_alias=AliasChoices("AUTH_USER_TENANT_SERVICE_TIMEOUT_SECONDS", "AUTH_ACCOUNT_SERVICE_TIMEOUT_SECONDS", "USER_TENANT_SERVICE_TIMEOUT_SECONDS", "ACCOUNT_SERVICE_TIMEOUT_SECONDS"))
    internal_service_token: str = Field(default="", repr=False)
    superadmin_emails: str = Field(default="", validation_alias=auth_env("SUPERADMIN_EMAILS"))

    secure_cookie: bool = Field(default=False, validation_alias=auth_env("SECURE_COOKIE"))
    refresh_cookie_name: str = Field(default="cf_refresh_token", validation_alias=auth_env("REFRESH_COOKIE_NAME"))

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    @property
    def superadmin_email_set(self) -> set[str]:
        return {email.strip().lower() for email in self.superadmin_emails.split(",") if email.strip()}

    @property
    def jwt_signing_key(self) -> str:
        if self.jwt_algorithm.upper().startswith("RS") and self.jwt_private_key:
            return self.jwt_private_key.replace("\\n", "\n")
        return self.jwt_secret

    @property
    def jwt_verification_key(self) -> str:
        if self.jwt_algorithm.upper().startswith("RS") and self.jwt_public_key:
            return self.jwt_public_key.replace("\\n", "\n")
        return self.jwt_secret


@lru_cache
def get_settings() -> Settings:
    return Settings()


