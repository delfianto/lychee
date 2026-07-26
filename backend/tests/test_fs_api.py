"""Storage-root filesystem browse API."""

from pathlib import Path

from fastapi.testclient import TestClient


def test_browse_root_lists_dirs_and_files(client: TestClient, tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    storage.mkdir(parents=True, exist_ok=True)
    (storage / "gallery").mkdir()
    (storage / "notes.txt").write_text("hi", encoding="utf-8")
    (storage / ".hidden").mkdir()

    resp = client.get("/api/fs")
    assert resp.status_code == 200
    body = resp.json()
    assert body["root"] == str(storage.resolve())
    assert body["path"] == str(storage.resolve())
    assert body["parent"] is None
    names = {e["name"]: e for e in body["entries"]}
    assert "gallery" in names and names["gallery"]["kind"] == "dir"
    assert "notes.txt" in names and names["notes.txt"]["kind"] == "file"
    assert ".hidden" not in names
    # Dirs before files.
    kinds = [e["kind"] for e in body["entries"]]
    assert kinds == sorted(kinds, key=lambda k: 0 if k == "dir" else 1)


def test_browse_subdir_and_parent(client: TestClient, tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    gallery = storage / "gallery" / "Artist"
    gallery.mkdir(parents=True)
    (gallery / "cover.jpg").write_bytes(b"x")

    resp = client.get("/api/fs", params={"path": str(gallery)})
    assert resp.status_code == 200
    body = resp.json()
    assert body["path"] == str(gallery.resolve())
    assert body["parent"] == str(gallery.parent.resolve())
    assert body["entries"][0]["name"] == "cover.jpg"

    # Relative path from root also works.
    rel = client.get("/api/fs", params={"path": "gallery/Artist"})
    assert rel.status_code == 200
    assert rel.json()["path"] == str(gallery.resolve())


def test_browse_rejects_path_escape(client: TestClient, tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    storage.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "outside"
    outside.mkdir()

    resp = client.get("/api/fs", params={"path": str(outside)})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "bad_request"

    # Classic traversal via relative segments.
    resp = client.get("/api/fs", params={"path": "../outside"})
    assert resp.status_code == 400


def test_browse_missing_path(client: TestClient, tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    storage.mkdir(parents=True, exist_ok=True)

    resp = client.get("/api/fs", params={"path": "nope"})
    assert resp.status_code == 404


def test_browse_file_is_rejected(client: TestClient, tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    storage.mkdir(parents=True, exist_ok=True)
    f = storage / "file.txt"
    f.write_text("x", encoding="utf-8")

    resp = client.get("/api/fs", params={"path": str(f)})
    assert resp.status_code == 400
    assert "directory" in resp.json()["error"]["message"]


def test_mkdir_creates_folder(client: TestClient, tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    storage.mkdir(parents=True, exist_ok=True)

    resp = client.post("/api/fs/mkdir", json={"parent": str(storage), "name": "manga"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["kind"] == "dir"
    assert body["name"] == "manga"
    assert body["path"] == str((storage / "manga").resolve())
    assert (storage / "manga").is_dir()

    # Shows up in the listing.
    listing = client.get("/api/fs").json()
    assert any(e["name"] == "manga" for e in listing["entries"])


def test_mkdir_conflict_and_validation(client: TestClient, tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    (storage / "exists").mkdir(parents=True)

    assert (
        client.post("/api/fs/mkdir", json={"parent": str(storage), "name": "exists"}).status_code
        == 409
    )
    assert (
        client.post("/api/fs/mkdir", json={"parent": str(storage), "name": "../x"}).status_code
        == 400
    )
    assert (
        client.post("/api/fs/mkdir", json={"parent": str(storage), "name": ".hidden"}).status_code
        == 400
    )
    assert client.post("/api/fs/mkdir", json={"parent": str(storage), "name": "  "}).status_code == 400
