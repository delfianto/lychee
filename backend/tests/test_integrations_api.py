"""Tests for providers, trackers, sync, and about endpoints."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from src.downloads.provider import RemoteChapter, register_provider
from src.tasks.queue import queue

from tests.support import make_series


class _SyncProvider:
    """A 'mangadex' provider whose feed has chapters 1–3."""

    id = "mangadex"

    def list_chapters(self, provider_series_id: str, *, language: str = "en") -> list[RemoteChapter]:
        return [RemoteChapter(f"r{n}", str(n), 1, None, "en") for n in (1, 2, 3)]

    def fetch_pages(self, chapter: RemoteChapter, *, data_saver: bool = False) -> list[bytes]:
        return []


def test_providers_list_and_update(client: TestClient) -> None:
    providers = client.get("/api/providers").json()
    assert any(p["id"] == "mangadex" for p in providers)

    updated = client.patch("/api/providers/mangadex", json={"enabled": False, "language": "ja"})
    assert updated.status_code == 200
    assert updated.json()["enabled"] is False
    assert updated.json()["language"] == "ja"

    # data_saver (download quality) round-trips
    assert client.patch("/api/providers/mangadex", json={"dataSaver": True}).json()["dataSaver"] is True


def test_trackers_connect_disconnect_and_toggle(client: TestClient) -> None:
    trackers = {t["id"]: t for t in client.get("/api/trackers").json()}
    assert {"anilist", "myanimelist", "mangaupdates", "novelupdates"} <= set(trackers)
    assert trackers["anilist"]["connected"] is False

    connected = client.post("/api/trackers/anilist/connect").json()
    assert connected["connected"] is True
    assert connected["accountName"]

    toggled = client.patch("/api/trackers/anilist", json={"syncOnRead": False})
    assert toggled.json()["syncOnRead"] is False

    assert client.delete("/api/trackers/anilist").status_code == 204
    assert client.get("/api/trackers").json()
    again = {t["id"]: t for t in client.get("/api/trackers").json()}
    assert again["anilist"]["connected"] is False


def test_sync_get_and_run(client: TestClient) -> None:
    initial = client.get("/api/sync").json()
    assert initial["lastSync"] is None
    assert initial["autoEveryMinutes"] == 360

    ran = client.post("/api/sync")
    assert ran.status_code == 202  # runs on the background queue now
    assert ran.json()["kind"] == "sync"
    queue.wait_idle()
    assert client.get("/api/sync").json()["lastSync"] is not None


def test_sync_flags_new_chapters(client: TestClient, db_session: Session) -> None:
    register_provider(_SyncProvider())  # remote feed has chapters 1–3
    series = make_series(db_session, title="Ongoing", kind="manga", chapter_count=1)  # local: ch 1
    series.provider = "mangadex"
    series.provider_series_id = "md-x"
    db_session.commit()

    assert client.post("/api/sync").status_code == 202
    queue.wait_idle()

    detail = client.get(f"/api/series/{series.id}").json()
    assert detail["availableChapters"] == 2  # chapters 2 & 3 are new upstream
    assert client.get("/api/sync").json()["newChapters"] == 2


def test_about(client: TestClient) -> None:
    about = client.get("/api/about").json()
    assert about["database"] == "SQLite"
    assert about["version"]
    assert about["uptimeSeconds"] >= 0


def test_unknown_provider_404(client: TestClient) -> None:
    assert client.patch("/api/providers/nope", json={"enabled": True}).status_code == 404
