"""Managed chapter layout and transaction-safe, recoverable volume moves.

A move links the existing archive at its new path without overwriting anything.
Both names remain readable until the database commits; rollback removes the new
name instead. A hidden journal resolves a process death before either cleanup.
No archive bytes are copied or re-encoded.
"""

from __future__ import annotations

import json
import os
import re
from contextlib import ExitStack, suppress
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from sqlalchemy import event, select
from sqlalchemy.orm import Session, SessionTransaction

from src.catalog.models import Book, Chapter, Library, Series
from src.core.exceptions import ConflictError
from src.core.logging import get_logger
from src.downloads.models import DownloadTask
from src.downloads.provider import RemoteChapter
from src.library.paths import is_provider_path
from src.media.artifacts import artifact_lock
from src.tasks.context import checkpoint
from src.tasks.queue import io_slot

logger = get_logger(__name__)
_STATE = "managed_chapter_moves"
_JOURNAL = ".lychee-moves"


def volume_directory(volume: int | None) -> str | None:
    return None if volume is None else f"Vol.{volume:02d}"


@dataclass
class _Move:
    journal: Path
    source: Path
    target: Path
    device: int
    inode: int

    def matches(self, path: Path) -> bool:
        if path.is_symlink():
            return False
        try:
            stat = path.stat()
        except FileNotFoundError:
            return False
        return path.is_file() and (stat.st_dev, stat.st_ino) == (self.device, self.inode)

    def finish(self, *, committed: bool) -> None:
        keep, remove = (self.target, self.source) if committed else (self.source, self.target)
        if not self.matches(keep):
            raise ConflictError(f"Cannot recover chapter move: archive changed at {keep}")
        if remove.exists() or remove.is_symlink():
            if not self.matches(remove):
                raise ConflictError(f"Cannot recover chapter move: archive changed at {remove}")
            remove.unlink()
        self.journal.unlink(missing_ok=True)
        # Only grouping folders are disposable, never the manga UUID directory.
        if remove.parent.name == "No Volume" or re.fullmatch(r"Vol\.\d+", remove.parent.name):
            with suppress(OSError):
                remove.parent.rmdir()


@dataclass
class _Transaction:
    locks: ExitStack = field(default_factory=ExitStack)
    libraries: set[str] = field(default_factory=set)
    moves: list[_Move] = field(default_factory=list)
    committed: bool = False


def hold_library_lock(session: Session, library_id: str) -> None:
    """Share the scan lock until this session's outer transaction finishes."""
    state: _Transaction = session.info.setdefault(_STATE, _Transaction())
    if library_id not in state.libraries:
        state.locks.enter_context(artifact_lock(f"scan:{library_id}"))
        state.libraries.add(library_id)
    # Closing even a read-only session must release its lock.
    if not session.in_transaction():
        session.begin()


@event.listens_for(Session, "after_commit")
def _committed(session: Session) -> None:
    state: _Transaction | None = session.info.get(_STATE)
    if state is not None and not session.in_nested_transaction():
        state.committed = True


@event.listens_for(Session, "after_transaction_end")
def _finish_transaction(session: Session, transaction: SessionTransaction) -> None:
    if transaction.parent is not None:
        return
    state: _Transaction | None = session.info.pop(_STATE, None)
    if state is None:
        return
    try:
        for move in reversed(state.moves):
            try:
                move.finish(committed=state.committed)
            except (OSError, ConflictError) as exc:
                # The journal survives for startup / pre-scan recovery.
                logger.warning(
                    "chapter_move_cleanup_failed", journal=str(move.journal), error=str(exc)
                )
    finally:
        state.locks.close()


def _contained(root: Path, relative: str) -> Path:
    path = root / relative
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ConflictError("Chapter move path escapes the library")
    if not path.resolve().is_relative_to(root) or path.is_symlink():
        raise ConflictError("Chapter move path escapes the library or is a symlink")
    return path


def recover_library_moves(session: Session, library: Library) -> None:
    """Called under the library lock, before scans/downloads or further moves."""
    if is_provider_path(library.path):
        return
    root = Path(library.path).resolve()
    directory = _contained(root, _JOURNAL)
    if not directory.is_dir():
        return
    for journal in sorted(directory.glob("*.json")):
        state: _Transaction | None = session.info.get(_STATE)
        if state is not None and any(move.journal == journal for move in state.moves):
            continue
        try:
            if journal.is_symlink():
                raise ConflictError("Chapter move journal is a symlink")
            data = json.loads(journal.read_text())
            source_rel, target_rel = data["source"], data["target"]
            book = session.get(Book, data["bookId"])
            if (
                book is None
                or book.library_id != library.id
                or book.path_rel not in (source_rel, target_rel)
            ):
                raise ConflictError("Chapter move journal does not match the catalog")
            move = _Move(
                journal,
                _contained(root, source_rel),
                _contained(root, target_rel),
                int(data["device"]),
                int(data["inode"]),
            )
            move.finish(committed=book.path_rel == target_rel)
        except (OSError, ValueError, KeyError, TypeError, ConflictError) as exc:
            # Never let a scan index unresolved aliases as two separate books.
            raise ConflictError(f"Cannot recover chapter move {journal.name}: {exc}") from exc


def recover_moves(session: Session) -> None:
    for library in session.scalars(select(Library)):
        if not is_provider_path(library.path):
            hold_library_lock(session, library.id)
            with io_slot():
                recover_library_moves(session, library)
            session.commit()


def _stage_move(session: Session, library: Library, book: Book, target_rel: str) -> None:
    root = Path(library.path).resolve()
    source, target = _contained(root, book.path_rel), _contained(root, target_rel)
    if not source.is_file():
        raise ConflictError(f"Cannot move missing chapter archive: {book.path_rel}")
    if target.exists() or target.is_symlink():
        raise ConflictError(f"Chapter destination already exists: {target_rel}")
    if (
        session.scalar(
            select(Book.id).where(
                Book.library_id == library.id,
                Book.path_rel == target_rel,
                Book.id != book.id,
                Book.deleted_at.is_(None),
            )
        )
        is not None
    ):
        raise ConflictError(f"Chapter destination is already indexed: {target_rel}")
    target.parent.mkdir(parents=True, exist_ok=True)
    directory = _contained(root, _JOURNAL)
    directory.mkdir(exist_ok=True)
    journal = directory / f"{uuid4().hex}.json"
    stat = source.stat()
    data = {
        "bookId": book.id,
        "source": book.path_rel,
        "target": target_rel,
        "device": stat.st_dev,
        "inode": stat.st_ino,
    }
    pending = journal.with_suffix(".pending")
    try:
        with open(pending, "x", opener=lambda path, flags: os.open(path, flags, 0o600)) as stream:
            json.dump(data, stream)
            stream.flush()
            os.fsync(stream.fileno())
        pending.replace(journal)
    finally:
        pending.unlink(missing_ok=True)
    try:
        # link() fails atomically if another file appears; replace()/rename() can overwrite it.
        os.link(source, target, follow_symlinks=False)
    except OSError:
        journal.unlink()
        raise
    state: _Transaction = session.info[_STATE]
    state.moves.append(_Move(journal, source, target, stat.st_dev, stat.st_ino))
    book.path_rel = target_rel


def reconcile_chapter_volumes(
    session: Session, series: Series, remotes: list[RemoteChapter], *, provider: str
) -> None:
    """Reconcile provider-owned CBZs only, never arbitrary scanned local files."""
    if provider != "mangadex" or series.provider != provider or not series.path_rel:
        return
    library = session.get(Library, series.library_id)
    if library is None or is_provider_path(library.path):
        return
    hold_library_lock(session, library.id)
    with io_slot():
        recover_library_moves(session, library)
    by_id = {remote.provider_chapter_id: remote for remote in remotes}
    chapters = list(
        session.scalars(
            select(Chapter).where(
                Chapter.series_id == series.id,
                Chapter.provider == provider,
                Chapter.provider_chapter_id.in_(by_id),
            )
        )
    )
    for chapter in chapters:
        checkpoint()
        book = session.get(Book, chapter.book_id)
        if book is None or book.deleted_at is not None or book.content_kind != "cbz":
            continue
        if book.library_id != library.id:
            continue
        # Downloads are one archive per chapter. Shared/local containers are untouched.
        if session.scalar(
            select(Chapter.id).where(Chapter.book_id == book.id, Chapter.id != chapter.id)
        ):
            continue
        path = Path(book.path_rel)
        series_path = Path(series.path_rel)
        if not path.is_relative_to(series_path):
            continue
        parts = path.relative_to(series_path).parts
        if len(parts) not in (1, 2) or not (
            path.name.startswith("Ch.")
            or path.name.startswith("Oneshot [")
            or path.name.startswith("Oneshot - ")
        ):
            continue
        if len(parts) == 2 and parts[0] != "No Volume" and not re.fullmatch(r"Vol\.\d+", parts[0]):
            continue
        remote = by_id[chapter.provider_chapter_id or ""]
        directory = volume_directory(remote.volume)
        target = series_path / directory / path.name if directory else series_path / path.name
        if target.as_posix() != book.path_rel:
            with io_slot():
                _stage_move(session, library, book, target.as_posix())
        chapter.volume = remote.volume

    # Active downloads re-read the index at publication; unclaimed rows get fresh
    # metadata now so resuming a paused queue cannot resurrect the old volume.
    for task in session.scalars(
        select(DownloadTask).where(
            DownloadTask.series_id == series.id,
            DownloadTask.provider == provider,
            DownloadTask.status.in_(("queued", "paused", "failed")),
        )
    ):
        data = task.remote_json or {}
        remote = by_id.get(str(data.get("provider_chapter_id", "")))
        if remote is not None:
            task.remote_json = {**data, "volume": remote.volume}
