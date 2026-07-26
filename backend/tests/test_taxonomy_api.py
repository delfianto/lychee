"""Tests for the taxonomy (Settings → Content) API."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.support import make_series


def test_list_includes_system_and_filters(client: TestClient) -> None:
    page = client.get("/api/taxonomy", params={"type": "content_rating"}).json()
    assert page["total"] == 4
    assert all(item["category"] == "content_rating" for item in page["items"])
    assert all(item["system"] for item in page["items"])

    genres = client.get("/api/taxonomy", params={"type": "genre", "q": "action"}).json()
    assert [i["id"] for i in genres["items"]] == ["action"]


def test_uses_count(client: TestClient, db_session: Session) -> None:
    make_series(db_session, title="A", tag_ids=["action"], content_rating="mature")
    make_series(db_session, title="B", tag_ids=["action"], content_rating="safe")
    db_session.commit()

    by_id = {
        i["id"]: i for i in client.get("/api/taxonomy", params={"pageSize": 100}).json()["items"]
    }
    assert by_id["action"]["uses"] == 2
    assert by_id["mature"]["uses"] == 1


def test_create_update_delete(client: TestClient) -> None:
    created = client.post("/api/taxonomy", json={"name": "Cyberpunk", "category": "genre"})
    assert created.status_code == 201
    tag_id = created.json()["id"]
    assert tag_id == "cyberpunk"

    updated = client.patch(f"/api/taxonomy/{tag_id}", json={"enabled": False, "name": "Cyber Punk"})
    assert updated.json()["enabled"] is False
    assert updated.json()["name"] == "Cyber Punk"

    assert client.delete(f"/api/taxonomy/{tag_id}").status_code == 204


def test_system_rows_are_protected(client: TestClient) -> None:
    assert client.patch("/api/taxonomy/safe", json={"name": "Renamed"}).status_code == 400
    assert client.delete("/api/taxonomy/safe").status_code == 400
    # enabling/disabling a system row is allowed
    assert client.patch("/api/taxonomy/safe", json={"enabled": False}).status_code == 200


def test_cannot_create_system_category(client: TestClient) -> None:
    assert (
        client.post("/api/taxonomy", json={"name": "X", "category": "demographic"}).status_code
        == 400
    )
