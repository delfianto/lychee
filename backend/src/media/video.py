"""Video helpers — poster frames via system ffmpeg (progressive MP4 only)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from src.core.logging import get_logger

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
            result = subprocess.run(  # noqa: S603 — fixed argv, no shell
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
                capture_output=True,
                timeout=45,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.warning("ffmpeg_poster_failed", path=str(path), error=str(exc))
            return None
        if result.returncode == 0 and result.stdout.startswith(b"\x89PNG"):
            return result.stdout
    logger.warning(
        "ffmpeg_poster_empty",
        path=str(path),
        stderr=(result.stderr.decode("utf-8", errors="replace")[:200] if result.stderr else ""),
    )
    return None
