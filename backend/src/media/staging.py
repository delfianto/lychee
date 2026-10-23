"""Fixed per-library workspaces; only finished archives enter the catalog tree."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory


@contextmanager
def workspace(library_root: Path, *, prefix: str) -> Iterator[Path]:
    root = library_root / "temp"
    root.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=f"{prefix}-", dir=root) as directory:
        yield Path(directory)
