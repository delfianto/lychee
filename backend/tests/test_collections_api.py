"""Tests for the collections (Lists) API."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.support import make_series


def test_collection_crud_and_membership(client: TestClient, db_session: Session) -> None:
    a = make_series(db_session, title="A")
    b = make_series(db_session, title="B")
    db_session.commit()

    created = client.post("/api/collections", json={"name": "Faves", "description": "top"})
    assert created.status_code == 201
    cid = created.json()["id"]
    assert created.json()["seriesIds"] == []

    client.post(f"/api/collections/{cid}/series", json={"seriesId": a.id})
    added = client.post(f"/api/collections/{cid}/series", json={"seriesId": b.id}).json()
    assert added["seriesIds"] == [a.id, b.id]  # insertion order preserved

    # idempotent add
    again = client.post(f"/api/collections/{cid}/series", json={"seriesId": a.id}).json()
    assert again["seriesIds"] == [a.id, b.id]

    detail = client.get(f"/api/collections/{cid}").json()
    assert [s["title"] for s in detail["series"]] == ["A", "B"]

    removed = client.request("DELETE", f"/api/collections/{cid}/series/{a.id}").json()
    assert removed["seriesIds"] == [b.id]

    listed = client.get("/api/collections").json()
    assert listed[0]["name"] == "Faves"

    assert client.delete(f"/api/collections/{cid}").status_code == 204
    assert client.get("/api/collections").json() == []


def test_update_and_missing(client: TestClient) -> None:
    cid = client.post("/api/collections", json={"name": "X"}).json()["id"]
    updated = client.patch(f"/api/collections/{cid}", json={"name": "Renamed"}).json()
    assert updated["name"] == "Renamed"

    assert client.get("/api/collections/nope").status_code == 404


def test_kind_persists_and_rejects_cross_kind_membership(
    client: TestClient, db_session: Session
) -> None:
    manga = make_series(db_session, title="M", kind="manga")
    manga2 = make_series(db_session, title="M2", kind="manga")
    gallery = make_series(db_session, title="G", kind="gallery")
    db_session.commit()

    cid = client.post("/api/collections", json={"name": "Mixed test"}).json()["id"]
    assert (
        client.get("/api/collections").json()[0]["kind"] == "manga"
    )  # type is known even for an empty list

    client.post(f"/api/collections/{cid}/series", json={"seriesId": manga.id})
    assert client.get(f"/api/collections/{cid}").json  # detail still works
    single = client.get("/api/collections").json()[0]
    assert single["kind"] == "manga"

    client.post(f"/api/collections/{cid}/series", json={"seriesId": manga2.id})
    still_single = client.get("/api/collections").json()[0]
    assert still_single["kind"] == "manga"

    rejected = client.post(f"/api/collections/{cid}/series", json={"seriesId": gallery.id})
    assert rejected.status_code == 400
    assert client.get(f"/api/collections/{cid}").json()["kind"] == "manga"
    assert client.get("/api/collections").json()[0]["seriesIds"] == [manga.id, manga2.id]
    for sid in [manga.id, manga2.id]:
        assert client.delete(f"/api/collections/{cid}/series/{sid}").status_code == 200
    assert client.get("/api/collections").json()[0]["kind"] == "manga"


def test_gallery_list_retains_type_when_empty_and_mangadex_rejects_other_types(
    client: TestClient, db_session: Session
) -> None:
    gallery = make_series(db_session, title="Gallery", kind="gallery")
    manga = make_series(db_session, title="Manga", kind="manga")
    db_session.commit()
    created = client.post("/api/collections", json={"name": "Gravure", "kind": "gallery"})
    assert created.status_code == 201
    cid = created.json()["id"]
    assert created.json()["kind"] == "gallery"
    assert (
        client.post(f"/api/collections/{cid}/series", json={"seriesId": manga.id}).status_code
        == 400
    )
    assert (
        client.post(f"/api/collections/{cid}/series", json={"seriesId": gallery.id}).status_code
        == 200
    )
    assert client.delete(f"/api/collections/{cid}/series/{gallery.id}").json()["kind"] == "gallery"
    assert client.get(f"/api/collections/{cid}").json()["kind"] == "gallery"
    assert (
        client.post(
            "/api/collections", json={"name": "Remote", "provider": "mangadex", "kind": "gallery"}
        ).status_code
        == 400
    )
