"""Library registration and scanning must respect provider and folder identities."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from src.catalog.models import Library
from src.providers.mangadex_account import _mangadex_library
from src.tasks.queue import queue


@pytest.mark.parametrize(
    "path", ["mangadex://follows", "mangadex:/follows", "https://host/books", "", "relative/books"]
)
def test_reject_nonlocal_registration(client: TestClient, path: str) -> None:
    response = client.post("/api/libraries", json={"name": "Invalid", "path": path})
    assert response.status_code == 400
    assert client.get("/api/libraries").json() == []


def test_duplicate_paths_and_symlinks(client: TestClient, tmp_path: Path) -> None:
    root = tmp_path / "books"
    root.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    created = client.post("/api/libraries", json={"name": "Books", "path": f" {root}/ "})
    assert created.status_code == 201
    assert created.json()["path"] == str(root)
    for path in (str(root), str(root / ".." / "books"), str(alias)):
        duplicate = client.post("/api/libraries", json={"name": "Duplicate", "path": path})
        assert duplicate.status_code == 409
        assert "already registered" in duplicate.json()["error"]["message"]
    library_id = created.json()["id"]
    assert (
        client.patch(f"/api/libraries/{library_id}", json={"path": str(alias)}).status_code == 200
    )
    other = client.post(
        "/api/libraries", json={"name": "Other", "path": str(tmp_path / "other")}
    ).json()
    assert (
        client.patch(f"/api/libraries/{other['id']}", json={"path": str(alias)}).status_code == 409
    )
    assert (
        client.patch(
            f"/api/libraries/{other['id']}", json={"path": "mangadex://follows"}
        ).status_code
        == 400
    )


def test_provider_is_managed_and_identified_by_path(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    local = Library(name="MangaDex", path=str(tmp_path), kind="manga")
    db_session.add(local)
    db_session.flush()
    provider = _mangadex_library(db_session)
    provider.name = "Renamed provider"
    db_session.commit()
    assert provider.id != local.id
    assert _mangadex_library(db_session).id == provider.id
    url = f"/api/libraries/{provider.id}"
    assert client.post(f"{url}/scan").status_code == 400
    assert client.patch(url, json={"path": str(tmp_path)}).status_code == 400
    assert client.delete(url).status_code == 400
    db_session.expire_all()
    assert db_session.get(Library, provider.id) is not None


@pytest.mark.parametrize("local", [False, True])
def test_scan_all_skips_provider_library(
    client: TestClient, db_session: Session, tmp_path: Path, local: bool
) -> None:
    provider = _mangadex_library(db_session)
    db_session.commit()
    if local:
        assert (
            client.post("/api/libraries", json={"name": "Local", "path": str(tmp_path)}).status_code
            == 201
        )
    response = client.post("/api/libraries/scan")
    assert response.status_code == 202
    queue.wait_idle()
    task = next(t for t in client.get("/api/tasks").json() if t["id"] == response.json()["id"])
    assert task["status"] == "done"
    assert task["result"]["booksAdded"] == 0
    db_session.refresh(provider)
    assert provider.last_scan_at is None
    libraries = client.get("/api/libraries").json()
    if local:
        assert (
            next(lib for lib in libraries if lib["path"] == str(tmp_path))["lastScan"] is not None
        )


def test_scan_all_with_no_libraries(client: TestClient) -> None:
    response = client.post("/api/libraries/scan")
    queue.wait_idle()
    task = next(t for t in client.get("/api/tasks").json() if t["id"] == response.json()["id"])
    assert task["status"] == "done"
    assert task["progress"] == 100
