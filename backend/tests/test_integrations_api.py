"""Tests for providers, trackers, sync, and about endpoints."""

from fastapi.testclient import TestClient


def test_providers_list_and_update(client: TestClient) -> None:
    providers = client.get("/api/providers").json()
    assert any(p["id"] == "mangadex" for p in providers)

    updated = client.patch("/api/providers/mangadex", json={"enabled": False, "language": "ja"})
    assert updated.status_code == 200
    assert updated.json()["enabled"] is False
    assert updated.json()["language"] == "ja"


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

    ran = client.post("/api/sync").json()
    assert ran["lastSync"] is not None
    assert ran["syncing"] is False


def test_about(client: TestClient) -> None:
    about = client.get("/api/about").json()
    assert about["database"] == "SQLite"
    assert about["version"]
    assert about["uptimeSeconds"] >= 0


def test_unknown_provider_404(client: TestClient) -> None:
    assert client.patch("/api/providers/nope", json={"enabled": True}).status_code == 404
