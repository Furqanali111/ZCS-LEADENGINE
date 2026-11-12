from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parent.parent / ".env", extra="ignore"
    )

    database_url: str
    test_database_url: str | None = None
    frontend_origin: str = "http://localhost:3000"
    export_dir: str = "./exports"
    npi_page_delay_seconds: float = 1
    brave_api_key: str | None = None
    enrich_page_delay_seconds: float = 1
    max_source_retries: int = 3
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
