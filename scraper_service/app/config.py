from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

SERVICE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILES = (str(SERVICE_ROOT / ".env"), str(PROJECT_ROOT / ".env"))


def scraper_env(name: str) -> AliasChoices:
    return AliasChoices(f"SCRAPER_{name}", name)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILES, env_file_encoding="utf-8", extra="ignore")

    app_name: str = Field(default="CreditFlow Scraper Service", validation_alias=scraper_env("APP_NAME"))
    environment: str = "local"
    log_level: str = "INFO"
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3005,http://127.0.0.1:3005"

    mongodb_url: str = Field(default="mongodb://localhost:27017/creditflow_scraper", validation_alias=AliasChoices("MONGODB_URL", "SCRAPER_MONGODB_URL"))
    mongodb_database: str = Field(default="creditflow_scraper", validation_alias=scraper_env("MONGODB_DATABASE"))
    mongodb_collection: str = Field(default="scraped_documents", validation_alias=scraper_env("MONGODB_COLLECTION"))

    rabbitmq_url: str = "amqp://guest:guest@localhost/"
    rabbitmq_exchange: str = "creditflow.events"
    rabbitmq_queue: str = Field(default="creditflow.scraper_service", validation_alias=scraper_env("RABBITMQ_QUEUE"))
    retry_queue: str = Field(default="creditflow.scraper_service.retry", validation_alias=scraper_env("RETRY_QUEUE"))
    dlq_queue: str = Field(default="creditflow.scraper_service.dlq", validation_alias=scraper_env("DLQ_QUEUE"))
    retry_delay_ms: int = Field(default=30000, validation_alias=scraper_env("RETRY_DELAY_MS"))
    max_retries: int = Field(default=3, validation_alias=scraper_env("MAX_RETRIES"))

    internal_service_token: str = Field(default="", repr=False)
    user_agent: str = Field(default="CreditFlowScraper/0.1 (+internal-use)", validation_alias=scraper_env("USER_AGENT"))
    per_domain_delay_seconds: float = Field(default=5.0, validation_alias=scraper_env("PER_DOMAIN_DELAY_SECONDS"))
    request_timeout_seconds: float = Field(default=30.0, validation_alias=scraper_env("REQUEST_TIMEOUT_SECONDS"))
    recurring_scan_interval_seconds: int = Field(default=60, validation_alias=scraper_env("RECURRING_SCAN_INTERVAL_SECONDS"))
    crawl4ai_base_directory: str = Field(default=str(SERVICE_ROOT / ".crawl4ai-runtime"), validation_alias=scraper_env("CRAWL4AI_BASE_DIRECTORY"))
    research_search_endpoint: str = Field(default="https://www.bing.com/news/search", validation_alias=scraper_env("RESEARCH_SEARCH_ENDPOINT"))
    research_default_max_sources: int = Field(default=5, validation_alias=scraper_env("RESEARCH_DEFAULT_MAX_SOURCES"))
    content_service_url: str = Field(default="http://localhost:8003", validation_alias=AliasChoices("SCRAPER_CONTENT_SERVICE_URL", "GATEWAY_CONTENT_SERVICE_URL", "CONTENT_SERVICE_URL"))
    openrouter_api_key: str = Field(default="", repr=False, validation_alias=AliasChoices("OPENROUTER_API_KEY", "SCRAPER_OPENROUTER_API_KEY"))
    openrouter_model: str = Field(default="", validation_alias=AliasChoices("OPENROUTER_MODEL", "SCRAPER_OPENROUTER_MODEL"))
    openrouter_fallback_model: str = Field(default="", validation_alias=AliasChoices("OPENROUTER_FALLBACK_MODEL", "SCRAPER_OPENROUTER_FALLBACK_MODEL"))
    openrouter_base_url: str = Field(default="https://openrouter.ai/api/v1", validation_alias=AliasChoices("OPENROUTER_BASE_URL", "SCRAPER_OPENROUTER_BASE_URL"))
    openrouter_timeout_seconds: float = Field(default=45.0, validation_alias=scraper_env("OPENROUTER_TIMEOUT_SECONDS"))

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
