"""Application configuration (Pydantic Settings)."""

from typing import Literal

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

_ = load_dotenv()


class Settings(BaseSettings):
    """App settings, loaded from environment / .env."""

    environment: Literal["development", "production"] = "development"

    # Database — SQLite by default (see ../notes/decisions/04-database-sqlite.md).
    database_url: str = "sqlite:///./lychee.db"

    # Storage root for generated binary files (thumbnails, etc.).
    storage_path: str = "./storage"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: list[str] = ["*"]

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["json", "console"] = "console"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
