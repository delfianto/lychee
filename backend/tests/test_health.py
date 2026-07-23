"""Smoke tests for the bare skeleton."""

from fastapi.testclient import TestClient


def test_health(client: TestClient) -> None:
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_root(client: TestClient) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["name"] == "lychee"
