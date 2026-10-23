"""Persisted storage selection and the real thumbnail serving dependency."""

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session
from src.catalog.deps import get_thumbnail_store
from src.core.config import settings
from src.main import app
from src.media.storage import thumbnail_root
from src.media.thumbnails import ThumbnailStore, ThumbVariant

from tests.test_media_api import _make_book_series

URL = "/api/libraries/thumbnail-storage"


def test_storage_selection_and_serving(
    client: TestClient, db_session: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    default = tmp_path / "storage"
    monkeypatch.setattr(settings, "storage_path", str(default))
    # Exercise the production dependency, including database preference lookup.
    del app.dependency_overrides[get_thumbnail_store]
    assert client.get(URL).json() == {
        "path": None,
        "defaultPath": str(default / "thumbnails"),
        "effectivePath": str(default / "thumbnails"),
    }
    custom = tmp_path / "custom" / "thumbs"
    response = client.put(URL, json={"path": f"  {custom}  "})
    assert response.status_code == 200
    assert response.json()["path"] == str(custom)
    assert custom.is_dir()
    assert thumbnail_root(db_session, default) == custom
    series, _ = _make_book_series(db_session, tmp_path, kind="manga", pages=1, with_chapter=True)
    assert client.get(f"/api/series/{series.id}/cover").status_code == 200
    assert ThumbnailStore(custom).exists(series.id, ThumbVariant.COVER)
    assert not (default / "thumbnails").exists()
    # Background writers resolve exactly the same selected folder.
    store = ThumbnailStore(thumbnail_root(db_session, default))
    store.generate("background", Image.new("RGB", (10, 10)), ThumbVariant.COVER)
    assert (custom / "ba" / "background.cover.avif").is_file()
    # A fresh request reads the persisted setting; resetting regenerates in default storage.
    assert client.get(URL).json()["path"] == str(custom)
    assert client.put(URL, json={"path": None}).json()["effectivePath"] == str(
        default / "thumbnails"
    )
    assert thumbnail_root(db_session, default) == default / "thumbnails"
    assert client.get(f"/api/series/{series.id}/cover").status_code == 200
    assert ThumbnailStore(default / "thumbnails").exists(series.id, ThumbVariant.COVER)
    assert store.exists(series.id, ThumbVariant.COVER)


@pytest.mark.parametrize("path", ["", "  ", "relative/folder", "\u0000bad"])
def test_invalid_path(client: TestClient, path: str) -> None:
    assert client.put(URL, json={"path": path}).status_code == 400
    assert client.get(URL).json()["path"] is None


def test_unwritable_or_file_path(client: TestClient, tmp_path: Path) -> None:
    target = tmp_path / "file"
    target.write_text("original")
    assert client.put(URL, json={"path": str(target)}).status_code == 400
    with patch("src.media.storage.TemporaryFile", side_effect=PermissionError):
        assert client.put(URL, json={"path": str(tmp_path / "denied")}).status_code == 400
    assert client.get(URL).json()["path"] is None
    assert client.put(URL, json={}).status_code == 422


def test_symlink_loop_is_rejected(client: TestClient, tmp_path: Path) -> None:
    target = tmp_path / "loop"
    target.symlink_to(target)
    assert client.put(URL, json={"path": str(target)}).status_code == 400
    assert client.get(URL).json()["path"] is None
