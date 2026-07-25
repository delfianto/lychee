"""Integrations API: providers, trackers, sync, about."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from src.core.persistence.database import DbSession
from src.integrations import service
from src.integrations.schema import (
    AboutOut,
    ProviderConnect,
    ProviderOut,
    ProviderUpdate,
    SyncOut,
    TrackerOut,
    TrackerUpdate,
)
from src.tasks.schema import TaskOut

router = APIRouter(prefix="/api", tags=["integrations"])


@router.get("/providers")
def list_providers(db: DbSession) -> list[ProviderOut]:
    return service.list_providers(db)


@router.patch("/providers/{provider_id}")
def update_provider(db: DbSession, provider_id: str, data: ProviderUpdate) -> ProviderOut:
    return service.update_provider(db, provider_id, data)


@router.post("/providers/{provider_id}/connect")
def connect_provider(db: DbSession, provider_id: str, data: ProviderConnect) -> ProviderOut:
    """Connect a MangaDex account (OAuth2 personal client); stores secrets encrypted."""
    return service.connect_provider(db, provider_id, data)


@router.post("/providers/{provider_id}/disconnect")
def disconnect_provider(db: DbSession, provider_id: str) -> ProviderOut:
    return service.disconnect_provider(db, provider_id)


@router.post("/providers/{provider_id}/import", status_code=status.HTTP_202_ACCEPTED)
def import_follows(db: DbSession, provider_id: str) -> TaskOut:
    """Import the connected account's follows + reading status in the background."""
    return service.import_follows(db, provider_id)


@router.get("/trackers")
def list_trackers(db: DbSession) -> list[TrackerOut]:
    return service.list_trackers(db)


@router.patch("/trackers/{tracker_id}")
def update_tracker(db: DbSession, tracker_id: str, data: TrackerUpdate) -> TrackerOut:
    return service.update_tracker(db, tracker_id, data)


@router.post("/trackers/{tracker_id}/connect")
def connect_tracker(db: DbSession, tracker_id: str) -> TrackerOut:
    return service.connect_tracker(db, tracker_id)


@router.delete("/trackers/{tracker_id}", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_tracker(db: DbSession, tracker_id: str) -> Response:
    service.disconnect_tracker(db, tracker_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/sync")
def get_sync(db: DbSession) -> SyncOut:
    return service.get_sync(db)


@router.post("/sync")
def run_sync(db: DbSession) -> SyncOut:
    return service.run_sync(db)


@router.get("/about")
def about() -> AboutOut:
    return service.about()
