"""Application configuration (Pydantic Settings)."""

from typing import Literal

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_ = load_dotenv()


class Settings(BaseSettings):
    """App settings, loaded from environment / .env."""

    environment: Literal["development", "production"] = "development"

    # Database — SQLite by default.
    database_url: str = "sqlite:///./lychee.db"

    # Storage root for generated binary files (thumbnails, etc.).
    storage_path: str = "./storage"

    # Passphrase used to encrypt stored provider secrets at rest.
    # Unset ⇒ connecting a MangaDex account is refused (no plaintext secrets).
    secret_key: str | None = Field(default=None, validation_alias="LYCHEE_SECRET_KEY")

    # Run migrations + seed on startup. Disabled in tests (they manage schema).
    auto_bootstrap: bool = True

    # AVIF encoding — worker processes for the encode pool. 1 = serial (in-process);
    # >1 fans a chapter's page encodes across a spawn ProcessPoolExecutor to use
    # multiple cores (encode is a pure function). Opt-in via LYCHEE_ENCODE_WORKERS.
    encode_workers: int = Field(default=1, ge=1, validation_alias="LYCHEE_ENCODE_WORKERS")

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
