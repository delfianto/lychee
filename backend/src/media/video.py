"""Video helpers — poster frames via system ffmpeg (progressive MP4 only)."""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from src.core.logging import get_logger
from src.tasks.context import OperationCancelled, checkpoint

logger = get_logger(__name__)

_FFMPEG = shutil.which("ffmpeg")


def ffmpeg_available() -> bool:
    return _FFMPEG is not None


def extract_poster_png(path: Path, *, seek_seconds: float = 1.0) -> bytes | None:
    """Grab one video frame as PNG bytes. Returns None if ffmpeg is missing or fails.

    Tries ``seek_seconds`` first (avoids pure-black openers), then t=0.
    """
    if _FFMPEG is None:
        logger.warning("ffmpeg_missing", path=str(path))
        return None
    for ss in (seek_seconds, 0.0):
        try:
            process = subprocess.Popen(  # noqa: S603 — fixed argv, no shell
                [
                    _FFMPEG,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-ss",
                    str(ss),
                    "-i",
                    str(path),
                    "-frames:v",
                    "1",
                    "-f",
                    "image2pipe",
                    "-vcodec",
                    "png",
                    "-",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            try:
                deadline = time.monotonic() + 45
                while True:
                    checkpoint()
                    try:
                        stdout, stderr = process.communicate(timeout=0.1)
                        break
                    except subprocess.TimeoutExpired:
                        if time.monotonic() >= deadline:
                            raise
            except BaseException:
                process.kill()
                process.communicate()
                raise
        except OperationCancelled:
            raise
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.warning("ffmpeg_poster_failed", path=str(path), error=str(exc))
            return None
        if process.returncode == 0 and stdout.startswith(b"\x89PNG"):
            return stdout
    logger.warning(
        "ffmpeg_poster_empty",
        path=str(path),
        stderr=(stderr.decode("utf-8", errors="replace")[:200] if stderr else ""),
    )
    return None
