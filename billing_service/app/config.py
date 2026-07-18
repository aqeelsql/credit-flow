from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

SERVICE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILES = (str(SERVICE_ROOT / ".env"), str(PROJECT_ROOT / ".env"))


def billing_env(name: str) -> AliasChoices:
    return AliasChoices(f"BILLING_{name}", name)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILES, env_file_encoding="utf-8", extra="ignore", populate_by_name=True)

    app_name: str = Field(default="CreditFlow Billing Service", validation_alias=billing_env("APP_NAME"))
    environment: str = "local"
    log_level: str = "INFO"
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    database_url: str = "postgresql://creditflow:creditflow@localhost:5432/creditflow"
    database_schema: str = Field(default="billing", validation_alias=billing_env("DATABASE_SCHEMA"))
    internal_service_token: str = Field(default="", repr=False)

    rabbitmq_url: str = "amqp://guest:guest@localhost/"
    rabbitmq_exchange: str = Field(default="billing_events", validation_alias=AliasChoices("BILLING_RABBITMQ_EXCHANGE"))
    outbox_poll_interval_seconds: float = Field(default=5.0, validation_alias=billing_env("OUTBOX_POLL_INTERVAL_SECONDS"))
    outbox_batch_size: int = Field(default=50, validation_alias=billing_env("OUTBOX_BATCH_SIZE"))
    dunning_grace_period_seconds: int = Field(default=259200, validation_alias=billing_env("DUNNING_GRACE_PERIOD_SECONDS"))

    stripe_secret_key: str = Field(default="", repr=False)
    stripe_webhook_secret: str = Field(default="", repr=False)
    checkout_success_url: str = Field(default="http://localhost:3000/billing?checkout=success", validation_alias=billing_env("CHECKOUT_SUCCESS_URL"))
    checkout_cancel_url: str = Field(default="http://localhost:3000/billing?checkout=cancelled", validation_alias=billing_env("CHECKOUT_CANCEL_URL"))
    frontend_base_url: str = Field(default="http://localhost:3000", validation_alias=billing_env("FRONTEND_BASE_URL"))

    stripe_price_free: str = Field(default="", validation_alias="STRIPE_PRICE_FREE")
    stripe_price_starter: str = Field(default="29", validation_alias="STRIPE_PRICE_STARTER")
    stripe_price_pro: str = Field(default="149", validation_alias="STRIPE_PRICE_PRO")
    stripe_price_team: str = Field(default="399", validation_alias="STRIPE_PRICE_TEAM")
    free_credits: int = Field(default=0, validation_alias=billing_env("FREE_CREDITS"))
    starter_credits: int = Field(default=4000, validation_alias=billing_env("STARTER_CREDITS"))
    pro_credits: int = Field(default=25000, validation_alias=billing_env("PRO_CREDITS"))
    team_credits: int = Field(default=90000, validation_alias=billing_env("TEAM_CREDITS"))

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    @property
    def plan_prices(self) -> dict[str, str]:
        return {"free": self.stripe_price_free, "starter": self.stripe_price_starter, "pro": self.stripe_price_pro, "team": self.stripe_price_team}

    @property
    def plan_credits(self) -> dict[str, int]:
        return {"free": self.free_credits, "starter": self.starter_credits, "pro": self.pro_credits, "team": self.team_credits}


@lru_cache
def get_settings() -> Settings:
    return Settings()
