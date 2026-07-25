"""Integrations API schemas: providers, trackers, sync, about."""

from __future__ import annotations

from pydantic import Field

from src.core.schema import CamelModel, UtcDatetime


class ProviderOut(CamelModel):
    id: str
    name: str
    enabled: bool
    language: str
    auto_match: bool
    fetch_covers: bool
    data_saver: bool
    connected: bool = False
    account_name: str | None = None


class ProviderUpdate(CamelModel):
    enabled: bool | None = None
    language: str | None = None
    auto_match: bool | None = None
    fetch_covers: bool | None = None
    data_saver: bool | None = None


class ProviderConnect(CamelModel):
    """MangaDex personal-client credentials (used once to obtain tokens; not stored)."""

    client_id: str
    client_secret: str
    username: str
    password: str


class TrackerConnect(CamelModel):
    """Begin a tracker OAuth flow: client app credentials + the registered redirect URI."""

    client_id: str
    client_secret: str
    redirect_uri: str


class TrackerAuthUrl(CamelModel):
    authorize_url: str


class TrackerCallback(CamelModel):
    """Complete the flow with the authorization code returned to the redirect URI."""

    code: str
    redirect_uri: str


class TrackerLogin(CamelModel):
    """Credentials login for non-OAuth trackers (e.g. MangaUpdates)."""

    username: str
    password: str


class TrackerOut(CamelModel):
    id: str
    name: str
    connected: bool
    sync_on_read: bool
    account_name: str | None = None
    auth_kind: str = "oauth"  # "oauth" | "credentials" | "unsupported" — drives the connect UI


class TrackerUpdate(CamelModel):
    sync_on_read: bool | None = None


class SyncOut(CamelModel):
    last_sync: UtcDatetime | None = None
    auto_every_minutes: int
    new_chapters: int
    syncing: bool


class AboutOut(CamelModel):
    version: str
    platform: str
    database: str
    started: UtcDatetime
    uptime_seconds: int


class ImportConfigOut(CamelModel):
    enabled: bool
    quality: int
    filename_pattern: str


class ImportConfigUpdate(CamelModel):
    enabled: bool | None = None
    quality: int | None = Field(default=None, ge=1, le=100)
    filename_pattern: str | None = None


class ImportRequest(CamelModel):
    """Import a container file or folder from a path on the server."""

    path: str
    kind: str = "manga"
