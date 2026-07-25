"""Integrations API schemas: providers, trackers, sync, about."""

from __future__ import annotations

from src.core.schema import CamelModel, UtcDatetime


class ProviderOut(CamelModel):
    id: str
    name: str
    enabled: bool
    language: str
    auto_match: bool
    fetch_covers: bool
    data_saver: bool


class ProviderUpdate(CamelModel):
    enabled: bool | None = None
    language: str | None = None
    auto_match: bool | None = None
    fetch_covers: bool | None = None
    data_saver: bool | None = None


class TrackerOut(CamelModel):
    id: str
    name: str
    connected: bool
    sync_on_read: bool
    account_name: str | None = None


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
