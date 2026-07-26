"""Outbound push: completing a chapter syncs read progress to a connected tracker."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from src.catalog.models import Chapter
from src.core.config import settings
from src.core.crypto import encrypt
from src.integrations.models import Tracker
from src.tasks.queue import queue
from src.trackers.base import TokenPair, register_tracker

from tests.support import make_series


class _RecordingTracker:
    id = "anilist"
    external_id_key = "al"
    auth_kind = "oauth"
    uses_pkce = False

    def __init__(self) -> None:
        self.pushes: list[dict[str, object]] = []

    def login(self, *, username: str, password: str) -> TokenPair:
        raise NotImplementedError

    def authorize_url(
        self, *, client_id: str, redirect_uri: str, state: str, code_challenge: str | None = None
    ) -> str:
        return "x"

    def exchange_code(
        self,
        *,
        code: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        code_verifier: str | None = None,
    ) -> TokenPair:
        raise NotImplementedError

    def account_name(self, access_token: str) -> str | None:
        return "u"

    def push(self, *, access_token: str, media_id: str, status: str, progress: int) -> None:
        self.pushes.append(
            {
                "access_token": access_token,
                "media_id": media_id,
                "status": status,
                "progress": progress,
            }
        )


def test_completing_a_chapter_pushes_to_connected_tracker(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "secret_key", "test-key")
    fake = _RecordingTracker()
    register_tracker(fake)

    series = make_series(db_session, title="Tracked", kind="manga", chapter_count=1, unread=1)
    series.external_ids_json = {"al": "555"}
    series.total_chapters = 1
    tracker = db_session.get(Tracker, "anilist")
    assert tracker is not None
    tracker.connected = True
    tracker.sync_on_read = True
    tracker.access_token_enc = encrypt("tok")
    db_session.commit()

    chapter = db_session.scalar(select(Chapter).where(Chapter.series_id == series.id))
    assert chapter is not None
    resp = client.put(f"/api/chapters/{chapter.id}/progress", json={"page": 1, "completed": True})
    assert resp.status_code in (200, 204)
    queue.wait_idle()

    assert len(fake.pushes) == 1
    assert fake.pushes[0]["media_id"] == "555"
    assert fake.pushes[0]["access_token"] == "tok"
    assert fake.pushes[0]["status"] == "completed"  # 1/1 read → completed
    assert fake.pushes[0]["progress"] == 1


def test_no_push_when_no_tracker_connected(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "secret_key", "test-key")
    fake = _RecordingTracker()
    register_tracker(fake)

    series = make_series(db_session, title="Untracked", kind="manga", chapter_count=1, unread=1)
    series.external_ids_json = {"al": "999"}
    db_session.commit()  # tracker left disconnected

    chapter = db_session.scalar(select(Chapter).where(Chapter.series_id == series.id))
    assert chapter is not None
    _ = client.put(f"/api/chapters/{chapter.id}/progress", json={"page": 1, "completed": True})
    queue.wait_idle()
    assert fake.pushes == []
