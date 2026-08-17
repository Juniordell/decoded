from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "decoded-api"
    version: str = "0.1.0"
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://decoded:decoded_dev@localhost:5432/decoded"
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"

    # Enrichment (all optional — pipeline still runs without them)
    openalex_email: Optional[str] = None  # for polite pool
    semantic_scholar_api_key: Optional[str] = None  # optional but recommended


settings = Settings()