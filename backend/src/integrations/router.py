"""Integrations API: metadata providers, reading trackers, sync, and about."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Form, Response, UploadFile, status

from src.core.persistence.database import DbSession
from src.downloads.deps import StorageRootDep
from src.integrations import about as about_svc
from src.integrations import import_config as import_svc
from src.integrations import local_import as local_import_svc
from src.integrations import providers as providers_svc
from src.integrations import sync as sync_svc
from src.integrations import trackers as trackers_svc
from src.integrations.schema import (
    AboutOut,
    ImportConfigOut,
    ImportConfigUpdate,
    ImportRequest,
    ProviderConnect,
    ProviderOut,
    ProviderUpdate,
    SyncOut,
    TrackerAuthUrl,
    TrackerCallback,
    TrackerConnect,
    TrackerLogin,
    TrackerOut,
    TrackerUpdate,
)
from src.providers import mangadex_account
from src.tasks.schema import TaskOut

router = APIRouter(prefix="/api", tags=["integrations"])


@router.get("/providers")
def list_providers(db: DbSession) -> list[ProviderOut]:
    return providers_svc.list_providers(db)


@router.patch("/providers/{provider_id}")
def update_provider(db: DbSession, provider_id: str, data: ProviderUpdate) -> ProviderOut:
    return providers_svc.update_provider(db, provider_id, data)


@router.post("/providers/{provider_id}/connect")
def connect_provider(db: DbSession, provider_id: str, data: ProviderConnect) -> ProviderOut:
    """Connect a MangaDex account (OAuth2 personal client); stores secrets encrypted."""
    return mangadex_account.connect(db, provider_id, data)


@router.post("/providers/{provider_id}/disconnect")
def disconnect_provider(db: DbSession, provider_id: str) -> ProviderOut:
    return mangadex_account.disconnect(db, provider_id)


@router.post("/providers/{provider_id}/import", status_code=status.HTTP_202_ACCEPTED)
def import_follows(db: DbSession, provider_id: str) -> TaskOut:
    """Import the connected account's follows + reading status in the background."""
    return mangadex_account.import_follows(db, provider_id)


@router.get("/trackers")
def list_trackers(db: DbSession) -> list[TrackerOut]:
    return trackers_svc.list_trackers(db)


@router.patch("/trackers/{tracker_id}")
def update_tracker(db: DbSession, tracker_id: str, data: TrackerUpdate) -> TrackerOut:
    return trackers_svc.update_tracker(db, tracker_id, data)


@router.post("/trackers/{tracker_id}/connect")
def connect_tracker(db: DbSession, tracker_id: str, data: TrackerConnect) -> TrackerAuthUrl:
    """Begin OAuth: store client credentials and return the authorize URL to visit."""
    return trackers_svc.begin_connect(db, tracker_id, data)


@router.post("/trackers/{tracker_id}/callback")
def tracker_callback(db: DbSession, tracker_id: str, data: TrackerCallback) -> TrackerOut:
    """Complete OAuth with the code from the redirect; stores the token encrypted."""
    return trackers_svc.complete_connect(db, tracker_id, data)


@router.post("/trackers/{tracker_id}/login")
def login_tracker(db: DbSession, tracker_id: str, data: TrackerLogin) -> TrackerOut:
    """Connect a credentials-based tracker (MangaUpdates) with username/password."""
    return trackers_svc.login(db, tracker_id, data)


@router.delete("/trackers/{tracker_id}", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_tracker(db: DbSession, tracker_id: str) -> Response:
    trackers_svc.disconnect(db, tracker_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/sync")
def get_sync(db: DbSession) -> SyncOut:
    return sync_svc.get_sync(db)


@router.post("/sync", status_code=status.HTTP_202_ACCEPTED)
def run_sync(db: DbSession) -> TaskOut:
    """Check matched series for new remote chapters in the background."""
    return sync_svc.run_sync(db)


@router.get("/import/config")
def get_import_config(db: DbSession) -> ImportConfigOut:
    return import_svc.get_import_config(db)


@router.patch("/import/config")
def update_import_config(db: DbSession, data: ImportConfigUpdate) -> ImportConfigOut:
    return import_svc.update_import_config(db, data)


@router.post("/import", status_code=status.HTTP_202_ACCEPTED)
def start_import(db: DbSession, storage: StorageRootDep, data: ImportRequest) -> TaskOut:
    """Import a local container file or folder in the background (transcode → AVIF)."""
    return local_import_svc.start_import(db, data, storage)


@router.post("/import/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_import(
    db: DbSession,
    storage: StorageRootDep,
    file: UploadFile,
    kind: Annotated[str, Form()] = "manga",
) -> TaskOut:
    """Import an uploaded container file in the background (transcode → AVIF)."""
    return await local_import_svc.start_upload_import(db, file, kind, storage)


@router.get("/about")
def about() -> AboutOut:
    return about_svc.info()
