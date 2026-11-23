"""Application settings, read from environment variables prefixed with APP_."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_", env_file=".env", extra="ignore")

    name: str = "Cloud-Native Items API"
    # Overridden in images by APP_VERSION (set from the release tag at build time).
    version: str = "1.5.0"
    environment: Literal["development", "test", "staging", "production"] = "development"
    debug: bool = False

    # Logging: one JSON object per line by default; "text" is easier to read locally.
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "text"] = "json"

    # Comma-separated SHA-256 hashes of valid API keys (never the keys themselves).
    # See app/core/security.py for the write-access policy.
    api_key_hashes: str = ""

    # SQLAlchemy URL. Compose and Kubernetes set a PostgreSQL URL, e.g.
    # postgresql+psycopg://app:<password>@db:5432/app. SQLite is for quick local runs.
    database_url: str = "sqlite:///./app.db"

    # Connection pool (ignored for SQLite). Per process: size + overflow is the
    # most connections one API replica will open.
    db_pool_size: int = 5
    db_max_overflow: int = 5
    db_pool_timeout: float = 10.0
    db_pool_recycle: int = 1800
    db_connect_timeout: int = 5
    db_statement_timeout_ms: int = 5000

    # Load shedding: requests in flight beyond this get an immediate 503 instead of
    # queueing until clients time out. Sized for one process (one CPU core); scale
    # out with replicas. 0 disables. Health checks and /metrics are exempt.
    max_concurrent_requests: int = 64

    api_prefix: str = "/api"
    default_page_size: int = 20
    max_page_size: int = 100

    @property
    def docs_enabled(self) -> bool:
        return self.environment != "production" or self.debug


@lru_cache
def get_settings() -> Settings:
    return Settings()
