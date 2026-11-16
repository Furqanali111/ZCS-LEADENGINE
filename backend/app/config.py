from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


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
    tavily_api_key: str | None = None
    enrich_page_delay_seconds: float = 1
    max_source_retries: int = 3
    log_level: str = "INFO"

    @property
    def session_database_url(self) -> str:
        """For migrations and the advisory lock: they need a session, so 6543 (transaction mode) becomes 5432."""
        url = make_url(self.database_url)
        if url.port == 6543:
            url = url.set(port=5432)
        return url.render_as_string(hide_password=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()
