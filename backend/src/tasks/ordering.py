"""Visible work order: active first, natural titles, numeric chapter labels."""

import re
from decimal import Decimal

_NUMBER = re.compile(r"([0-9]+(?:\.[0-9]+)?)")
_CHAPTER = re.compile(r"^ch(?:apter)?(?:\.\s*|\s+)", re.IGNORECASE)
_STATUS = {
    "running": 0,
    "downloading": 0,
    "cancelling": 0,
    "queued": 1,
    "paused": 2,
    "failed": 3,
    "cancelled": 4,
    "done": 5,
}


def work_status_rank(status: str) -> int:
    return _STATUS.get(status, 6)


def natural_key(value: str) -> tuple[tuple[int, str | Decimal], ...]:
    return tuple(
        (1, Decimal(part)) if index % 2 else (0, part.casefold())
        for index, part in enumerate(_NUMBER.split(value))
    )


def chapter_key(label: str) -> tuple[int, tuple[tuple[int, str | Decimal], ...]]:
    number = _CHAPTER.sub("", label).strip()
    if re.fullmatch(r"[+-]?[0-9]+(?:\.[0-9]+)?", number):
        return 0, ((1, Decimal(number)),)
    return 1, natural_key(number)
