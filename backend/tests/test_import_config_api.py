"""Tests for the Local-import config singleton (Settings → Local import)."""

from fastapi.testclient import TestClient


def test_defaults(client: TestClient) -> None:
    assert client.get("/api/import/config").json() == {
        "enabled": False,
        "quality": 75,
        "filenamePattern": "",
    }


def test_patch_persists(client: TestClient) -> None:
    resp = client.patch(
        "/api/import/config",
        json={"enabled": True, "quality": 60, "filenamePattern": "{series} - c{chapter}"},
    )
    assert resp.status_code == 200
    assert resp.json() == {
        "enabled": True,
        "quality": 60,
        "filenamePattern": "{series} - c{chapter}",
    }
    # persists across requests
    assert client.get("/api/import/config").json()["quality"] == 60


def test_partial_update_leaves_others(client: TestClient) -> None:
    assert client.patch("/api/import/config", json={"quality": 50}).status_code == 200
    data = client.get("/api/import/config").json()
    assert data["quality"] == 50
    assert data["enabled"] is False  # untouched


def test_quality_out_of_range_rejected(client: TestClient) -> None:
    assert client.patch("/api/import/config", json={"quality": 150}).status_code == 422
    assert client.patch("/api/import/config", json={"quality": 0}).status_code == 422
