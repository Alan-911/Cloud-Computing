"""Application settings, read from environment variables prefixed with APP_."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_", env_file=".env", extra="ignore")

    name: str = "Cloud-Native Items API"
    version: str = "1.1.0"
    environment: Literal["development", "test", "staging", "production"] = "development"
    debug: bool = False

    # SQLite for now; Phase 02 switches this to a PostgreSQL URL.
    database_url: str = "sqlite:///./app.db"

    api_prefix: str = "/api"
    default_page_size: int = 20
    max_page_size: int = 100

    @property
    def docs_enabled(self) -> bool:
        return self.environment != "production" or self.debug


@lru_cache
def get_settings() -> Settings:
    return Settings()
