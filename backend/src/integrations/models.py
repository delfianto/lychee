"""Integration config: metadata providers, trackers, and the sync singleton.

All three use stable slug ids (``mangadex``, ``anilist``, …) so seeds and the API
reference them by a readable key. Seeded idempotently at startup.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.persistence.base_model import Base, TimestampMixin


class Provider(Base, TimestampMixin):
    """A metadata provider (e.g. MangaDex) and its per-provider options."""

    __tablename__ = "provider"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # slug
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    language: Mapped[str] = mapped_column(String(16), default="en", nullable=False)
    auto_match: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    fetch_covers: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Download the lighter "data-saver" (JPEG) pages instead of original quality.
    data_saver: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # OAuth2 account: client secret + refresh token are stored encrypted.
    account_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    client_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    client_secret_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)


class Tracker(Base, TimestampMixin):
    """An outbound reading tracker (AniList / MangaUpdates / MyAnimeList)."""

    __tablename__ = "tracker"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # slug
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    connected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sync_on_read: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    account_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # OAuth2: client secret + tokens stored encrypted (see core.crypto).
    client_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    client_secret_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    pkce_verifier: Mapped[str | None] = mapped_column(String(128), nullable=True)  # transient (MAL)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SyncState(Base, TimestampMixin):
    """Singleton row (id ``default``) backing the Downloads → Sync card."""

    __tablename__ = "sync_state"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default="default")
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    auto_every_minutes: Mapped[int] = mapped_column(Integer, default=360, nullable=False)  # 6h
    syncing: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    new_chapters: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class ImportConfig(Base, TimestampMixin):
    """Singleton row (id ``default``) backing Settings → Local import."""

    __tablename__ = "import_config"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default="default")
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # AVIF quality (1–100) for transcoded import pages.
    quality: Mapped[int] = mapped_column(Integer, default=75, nullable=False)
    # Token-template pattern to derive metadata from filenames (empty → built-in parser).
    filename_pattern: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    # Saved, reusable filename-pattern presets: a list of {"name", "pattern"}.
    pattern_presets: Mapped[list[dict[str, str]] | None] = mapped_column(
        JSON, default=list, nullable=True
    )
