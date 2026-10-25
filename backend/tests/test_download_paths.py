"""Managed layout, metadata reconciliation, and interrupted filesystem moves."""

from __future__ import annotations

import io
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session
from src.catalog.models import Book, Chapter, ProviderChapter, Series
from src.catalog.remote_chapters import upsert_provider_chapters
from src.core.exceptions import ConflictError
from src.downloads.downloader import chapter_path_rel
from src.downloads.models import DownloadTask
from src.downloads.paths import hold_library_lock, recover_library_moves, recover_moves
from src.downloads.provider import RemoteChapter, register_provider
from src.ingest.scanner import scan_library
from src.library.service import _scan_one_work
from src.progress.models import ReadingProgress
from src.tasks.context import Operation, OperationCancelled, current_operation
from src.tasks.queue import queue

from tests.support import ensure_manga_library

UUID = "f6fc7b4d-085b-4075-9263-345631e6ac93"
PID = "abcdef01-0000-0000-0000-000000000001"


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (24, 32), (60, 90, 120)).save(buf, "PNG")
    return buf.getvalue()


def _remote(volume: int | None, *, number: str = "1") -> RemoteChapter:
    return RemoteChapter(PID, number, volume, None, "en")


def _managed(session: Session, root: Path, *, folder: str = "No Volume", number: str = "1"):
    library = ensure_manga_library(session, root)
    series = Series(
        library_id=library.id,
        kind="manga",
        title="Test",
        sort_title="test",
        provider="mangadex",
        provider_series_id=UUID,
        path_rel=UUID,
    )
    session.add(series)
    session.flush()
    filename = "Ch.1.cbz" if number == "1" else "Oneshot [abcdef01].cbz"
    relative = (Path(UUID) / folder / filename).as_posix()
    source = root / relative
    source.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(source, "w") as archive:
        archive.writestr("001.png", _png())
    book = Book(
        series_id=series.id,
        library_id=library.id,
        path_rel=relative,
        content_kind="cbz",
        page_count=1,
        file_size=source.stat().st_size,
    )
    session.add(book)
    session.flush()
    chapter = Chapter(
        series_id=series.id,
        book_id=book.id,
        volume=None,
        number=number,
        number_sort=1 if number == "1" else None,
        page_count=1,
        provider="mangadex",
        provider_chapter_id=PID,
    )
    session.add(chapter)
    session.flush()
    progress = ReadingProgress(
        series_id=series.id, chapter_id=chapter.id, current_page=1, completed=True
    )
    session.add(progress)
    session.commit()
    return library, series, book, chapter, progress, source


@pytest.mark.parametrize(
    ("number", "volume", "expected"),
    [
        ("1", None, "Ch.1.cbz"),
        ("Oneshot", None, "Oneshot [abcdef01].cbz"),
        ("Oneshot", 2, "Vol.02/Oneshot [abcdef01].cbz"),
        ("1", 0, "Vol.00/Ch.1.cbz"),
        ("1", 3, "Vol.03/Ch.1.cbz"),
    ],
)
def test_download_layout(number: str, volume: int | None, expected: str) -> None:
    series = Series(id="local", provider="mangadex", provider_series_id=UUID)
    assert chapter_path_rel(series, _remote(volume, number=number)) == f"{UUID}/{expected}"


@pytest.mark.parametrize(
    ("folder", "volume", "number"),
    [
        ("No Volume", None, "1"),
        ("No Volume", 1, "1"),
        ("", 2, "1"),
        ("Vol.01", 2, "1"),
        ("Vol.01", None, "1"),
        ("No Volume", None, "Oneshot"),
        ("", 3, "Oneshot"),
    ],
)
def test_sync_moves_archive_preserving_identity_progress_and_scan(
    db_session: Session, tmp_path: Path, folder: str, volume: int | None, number: str
) -> None:
    library, series, book, chapter, progress, source = _managed(
        db_session, tmp_path / "manga", folder=folder, number=number
    )
    ids = (book.id, chapter.id, progress.id)
    inode, content = source.stat().st_ino, source.read_bytes()
    remote = _remote(volume, number=number)
    upsert_provider_chapters(db_session, series, [remote])
    target = Path(library.path) / UUID
    target = (
        target / f"Vol.{volume:02d}" / source.name if volume is not None else target / source.name
    )
    assert source.exists()  # old DB snapshots remain readable until commit
    assert target.read_bytes() == content
    db_session.commit()
    assert not source.exists() or source == target
    assert target.stat().st_ino == inode
    assert book.path_rel == str(target.relative_to(library.path))
    assert chapter.volume == volume
    assert (book.id, chapter.id, progress.id) == ids
    assert progress.current_page == 1 and progress.completed
    assert not list((Path(library.path) / ".lychee-moves").glob("*.json"))
    # Repeated sync and subsequent scanning must not create replacement identities.
    upsert_provider_chapters(db_session, series, [remote])
    db_session.commit()
    scan_library(db_session, library)
    db_session.commit()
    assert db_session.scalars(select(Book).where(Book.deleted_at.is_(None))).all() == [book]
    assert db_session.scalars(select(Chapter)).all() == [chapter]
    assert chapter.number == number and chapter.volume == volume
    assert progress.completed and progress.chapter_id == chapter.id


@pytest.mark.parametrize("close", [False, True])
def test_rollback_or_close_removes_only_new_link(
    db_engine: Engine, tmp_path: Path, close: bool
) -> None:
    with Session(db_engine) as session:
        library, series, book, chapter, _, source = _managed(session, tmp_path / "manga")
        old_path, book_id, chapter_id = book.path_rel, book.id, chapter.id
        target = Path(library.path) / UUID / "Vol.01" / source.name
        upsert_provider_chapters(session, series, [_remote(1)])
        assert source.samefile(target)
        session.close() if close else session.rollback()
        assert source.exists() and not target.exists()
        assert session.get(Book, book_id).path_rel == old_path  # type: ignore[union-attr]
        assert session.get(Chapter, chapter_id).volume is None  # type: ignore[union-attr]
        hold_library_lock(session, library.id)  # previous transaction released its lock
        session.rollback()


@pytest.mark.parametrize("collision", ["file", "symlink", "indexed", "missing", "outside"])
def test_move_rejects_unsafe_paths_without_losing_original(
    db_session: Session, tmp_path: Path, collision: str
) -> None:
    library, series, book, chapter, _, source = _managed(db_session, tmp_path / "manga")
    target = Path(library.path) / UUID / "Vol.01" / source.name
    target.parent.mkdir()
    if collision == "file":
        target.write_bytes(b"other archive")
    elif collision == "symlink":
        target.symlink_to(tmp_path / "missing")
    elif collision == "indexed":
        db_session.add(
            Book(
                series_id=series.id,
                library_id=library.id,
                path_rel=str(target.relative_to(library.path)),
                content_kind="cbz",
            )
        )
    elif collision == "missing":
        source.unlink()
    else:
        target.parent.rmdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        target.parent.symlink_to(outside, target_is_directory=True)
    db_session.commit()
    with pytest.raises(ConflictError):
        upsert_provider_chapters(db_session, series, [_remote(1)])
    db_session.rollback()
    assert chapter.volume is None
    assert source.exists() == (collision != "missing")
    if collision == "file":
        assert target.read_bytes() == b"other archive"


def _interrupted(session: Session, root: Path, *, committed: bool, linked: bool = True):
    library, _, book, _, _, source = _managed(session, root)
    target = root / UUID / "Vol.01" / source.name
    target.parent.mkdir()
    stat = source.stat()
    directory = root / ".lychee-moves"
    directory.mkdir()
    journal = directory / "interrupted.json"
    journal.write_text(
        json.dumps(
            {
                "bookId": book.id,
                "source": book.path_rel,
                "target": str(target.relative_to(root)),
                "device": stat.st_dev,
                "inode": stat.st_ino,
            }
        )
    )
    if linked:
        os.link(source, target)
    if committed:
        book.path_rel = str(target.relative_to(root))
        session.commit()
    return library, book, source, target, journal


@pytest.mark.parametrize(("committed", "linked"), [(False, False), (False, True), (True, True)])
def test_interrupted_move_recovers_from_database_path(
    db_session: Session, tmp_path: Path, committed: bool, linked: bool
) -> None:
    library, book, source, target, journal = _interrupted(
        db_session, tmp_path / "manga", committed=committed, linked=linked
    )
    recover_moves(db_session)
    assert source.exists() != committed
    assert target.exists() == committed
    assert not journal.exists()
    assert (Path(library.path) / book.path_rel).is_file()


def test_scan_recovers_interrupted_move_before_indexing(
    db_session: Session, tmp_path: Path
) -> None:
    library, book, source, target, _ = _interrupted(db_session, tmp_path / "manga", committed=False)
    _scan_one_work(library.id, tmp_path / "storage")(db_session, lambda *_: None)
    assert source.exists() and not target.exists()
    assert db_session.scalars(select(Book).where(Book.deleted_at.is_(None))).all() == [book]


def test_recovery_refuses_to_delete_replaced_file(db_session: Session, tmp_path: Path) -> None:
    library, _, source, target, journal = _interrupted(
        db_session, tmp_path / "manga", committed=True
    )
    source.unlink()
    source.write_bytes(b"replacement")
    with pytest.raises(ConflictError, match="archive changed"):
        recover_library_moves(db_session, library)
    assert source.read_bytes() == b"replacement" and target.exists() and journal.exists()


def test_sync_updates_pending_volume_and_leaves_absent_or_unmanaged_chapters(
    db_session: Session, tmp_path: Path
) -> None:
    _, series, book, chapter, _, source = _managed(db_session, tmp_path / "manga")
    task = DownloadTask(
        series_id=series.id,
        provider="mangadex",
        chapter_label="Ch. 1",
        status="paused",
        remote_json=asdict(_remote(None)),
    )
    db_session.add(task)
    db_session.commit()
    upsert_provider_chapters(db_session, series, [])
    db_session.commit()
    assert chapter.volume is None and source.exists()  # absence isn't a metadata correction
    chapter.provider_chapter_id = None
    db_session.commit()
    upsert_provider_chapters(db_session, series, [_remote(1)])
    db_session.commit()
    assert chapter.volume is None and book.path_rel.endswith("No Volume/Ch.1.cbz")
    assert source.exists() and task.remote_json is not None and task.remote_json["volume"] == 1


def test_cancellation_rolls_back_already_staged_moves(db_session: Session, tmp_path: Path) -> None:
    _, series, book, chapter, _, source = _managed(db_session, tmp_path / "manga")
    upsert_provider_chapters(db_session, series, [_remote(1)])
    token = current_operation.set(
        Operation("test", lambda: (_ for _ in ()).throw(OperationCancelled()), lambda *_: None)
    )
    try:
        with pytest.raises(OperationCancelled):
            upsert_provider_chapters(db_session, series, [_remote(2)])
        db_session.rollback()
    finally:
        current_operation.reset(token)
    assert source.exists() and chapter.volume is None
    assert book.path_rel.endswith("No Volume/Ch.1.cbz")


def test_download_publishes_latest_volume_after_sync_during_fetch(
    client: TestClient, db_engine: Engine, db_session: Session, tmp_path: Path
) -> None:
    started, release = threading.Event(), threading.Event()

    class Provider:
        id = "mangadex"

        def list_chapters(self, *args, **kwargs):
            return [_remote(None)]

        def fetch_pages(self, *args, **kwargs):
            started.set()
            assert release.wait(10)
            return [_png()]

    register_provider(Provider())
    library = ensure_manga_library(db_session, tmp_path / "manga")
    series = Series(
        library_id=library.id,
        kind="manga",
        title="Test",
        sort_title="test",
        provider="mangadex",
        provider_series_id=UUID,
        path_rel=UUID,
    )
    db_session.add(series)
    db_session.commit()
    try:
        assert client.post("/api/downloads", json={"seriesId": series.id}).status_code == 202
        assert started.wait(10)
        with Session(db_engine) as sync_session:
            synced_series = sync_session.get(Series, series.id)
            assert synced_series is not None
            upsert_provider_chapters(sync_session, synced_series, [_remote(2)])
            sync_session.commit()
    finally:
        release.set()
        queue.wait_idle()
    assert all(task["status"] == "done" for task in client.get("/api/downloads").json())
    db_session.expire_all()
    chapter = db_session.scalar(select(Chapter).where(Chapter.series_id == series.id))
    assert chapter is not None and chapter.volume == 2
    assert (Path(library.path) / UUID / "Vol.02" / "Ch.1.cbz").exists()
    assert not (Path(library.path) / UUID / "Ch.1.cbz").exists()
    assert (
        db_session.scalar(
            select(ProviderChapter.volume).where(ProviderChapter.series_id == series.id)
        )
        == 2
    )


@pytest.mark.parametrize("number", ["1", "Oneshot"])
def test_actual_no_volume_download_is_at_series_root(
    client: TestClient, db_session: Session, tmp_path: Path, number: str
) -> None:
    class Provider:
        id = "mangadex"

        def list_chapters(self, *args, **kwargs):
            return [_remote(None, number=number)]

        def fetch_pages(self, *args, **kwargs):
            return [_png()]

    register_provider(Provider())
    library = ensure_manga_library(db_session, tmp_path / "manga")
    series = Series(
        library_id=library.id,
        kind="manga",
        title="Test",
        sort_title="test",
        provider="mangadex",
        provider_series_id=UUID,
    )
    db_session.add(series)
    db_session.commit()
    assert client.post("/api/downloads", json={"seriesId": series.id}).status_code == 202
    queue.wait_idle()
    tasks = client.get("/api/downloads").json()
    assert len(tasks) == 1 and tasks[0]["status"] == "done"
    chapter = db_session.scalar(select(Chapter).where(Chapter.series_id == series.id))
    assert chapter is not None
    book = db_session.get(Book, chapter.book_id)
    assert book is not None and Path(book.path_rel).parent == Path(UUID)
    assert not (Path(library.path) / UUID / "No Volume").exists()
    assert client.get(f"/api/chapters/{chapter.id}/pages/1").status_code == 200


def test_scan_waits_for_move_commit(
    db_session: Session, db_engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.library import service
    from src.media.artifacts import artifact_lock

    library, series, book, _, _, source = _managed(db_session, tmp_path / "manga")
    library_id, book_id = library.id, book.id
    upsert_provider_chapters(db_session, series, [_remote(1)])
    waiting, entered = threading.Event(), threading.Event()

    def checked_lock(key: str):
        waiting.set()
        return artifact_lock(key)

    original_scan = service.scan_library

    def checked_scan(*args, **kwargs):
        entered.set()
        return original_scan(*args, **kwargs)

    monkeypatch.setattr(service, "artifact_lock", checked_lock)
    monkeypatch.setattr(service, "scan_library", checked_scan)

    def scan():
        with Session(db_engine) as session:
            return _scan_one_work(library_id, tmp_path / "storage")(session, lambda *_: None)

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(scan)
        try:
            assert waiting.wait(5)
            assert not entered.is_set() and not future.done()
        finally:
            db_session.commit()
        result = future.result(timeout=10)
    assert result is not None
    assert result["booksAdded"] == 0 and result["booksRemoved"] == 0
    assert not source.exists()
    db_session.expire_all()
    assert db_session.get(Book, book_id) is not None


def test_link_failure_keeps_original_and_releases_lock(
    db_session: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library, series, book, _, _, source = _managed(db_session, tmp_path / "manga")

    def fail(*args, **kwargs):
        raise OSError("link unavailable")

    monkeypatch.setattr("src.downloads.paths.os.link", fail)
    with pytest.raises(OSError, match="link unavailable"):
        upsert_provider_chapters(db_session, series, [_remote(1)])
    db_session.rollback()
    assert source.exists() and book.path_rel.endswith("No Volume/Ch.1.cbz")
    assert not list((Path(library.path) / ".lychee-moves").glob("*.json"))
    hold_library_lock(db_session, library.id)
    db_session.rollback()
