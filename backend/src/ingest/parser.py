"""Filename / volume-chapter parser.

A prioritized regex cascade over the path segments below the series folder plus
the filename. The key trick is **series-name subtraction**: strip the
known series title first, then hunt for numbers in the remainder — this kills the
classic title-number false positives (``Gundam 0079``, ``7 Seeds``). Specials
(Omake/Extra/…) become decimal offsets; a base-less special returns
``number_sort=None`` for the series-level ordering pass to place.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_SPECIALS = ("omake", "extra", "epilogue", "prologue", "bonus", "special", "side story", "sp")

# Bracketed groups / common release noise stripped before number hunting.
_BRACKETS = re.compile(r"[\[\{（(].*?[\]\}）)]")
_NOISE = re.compile(
    r"\b(?:digital|scan(?:lation)?|web(?:rip)?|dl|hd|uncensored|c2c|v\d+\s*fixed)\b",
    re.IGNORECASE,
)
_YEAR = re.compile(r"(?:19|20)\d{2}")
_VOLUME = re.compile(r"\b(?:vol(?:ume)?|v)\.?\s*(\d{1,4})\b", re.IGNORECASE)
_COMBINED = re.compile(r"\bv(\d{1,4})\s*c(\d{1,4}(?:\.\d+)?)\b", re.IGNORECASE)
_CHAPTER = re.compile(
    r"\b(?:ch(?:apter)?|chap|ep(?:isode)?|c|#)\.?\s*(\d{1,5}(?:\.\d+)?)\b", re.IGNORECASE
)
_RANGE = re.compile(r"(\d{1,5}(?:\.\d+)?)\s*-\s*(\d{1,5}(?:\.\d+)?)")
_BARE = re.compile(r"(?<![\d.])(\d{1,5}(?:\.\d+)?)(?![\d.])")


@dataclass(frozen=True)
class ParsedName:
    """Result of parsing a book's on-disk name."""

    number: str | None  # display label, e.g. "10.5", "1-4", "Omake"
    number_sort: float | None # ordering key; None → assign during ordering
    volume: int | None
    year: int | None
    special: bool
    label: str | None  # special label, e.g. "Omake"


def _strip_ext(name: str) -> str:
    return re.sub(r"\.(cbz|cbr|zip|rar|7z|pdf|epub)$", "", name, flags=re.IGNORECASE)


def _normalize(text: str, series_name: str) -> str:
    """Lowercase, drop brackets/noise, subtract the series name, collapse space."""
    out = text.replace("_", " ")
    out = _BRACKETS.sub(" ", out)
    out = _NOISE.sub(" ", out)
    out = out.lower()
    series = re.sub(r"\s+", " ", series_name.strip().lower())
    if series:
        out = out.replace(series, " ")
    return re.sub(r"\s+", " ", out).strip()


def _find_special(text: str) -> tuple[bool, str | None]:
    for marker in _SPECIALS:
        if re.search(rf"\b{re.escape(marker)}\b", text):
            return True, marker.title()
    return False, None


def _find_volume(text: str) -> int | None:
    combined = _COMBINED.search(text)
    if combined:
        return int(combined.group(1))
    match = _VOLUME.search(text)
    return int(match.group(1)) if match else None


def _find_number(text: str) -> tuple[str | None, float | None]:
    combined = _COMBINED.search(text)
    if combined:
        return _trim(combined.group(2)), float(combined.group(2))
    rng = _RANGE.search(text)
    if rng:
        return f"{_trim(rng.group(1))}-{_trim(rng.group(2))}", float(rng.group(1))
    chap = _CHAPTER.search(text)
    if chap:
        return _trim(chap.group(1)), float(chap.group(1))
    # Bare-number fallback: after volume/series subtraction, a lone number is the chapter.
    without_volume = _VOLUME.sub(" ", text)
    bare = _BARE.search(without_volume)
    if bare:
        return _trim(bare.group(1)), float(bare.group(1))
    return None, None


def _trim(num: str) -> str:
    """Drop leading zeros / trailing ``.0`` for a clean display label."""
    value = float(num)
    return str(int(value)) if value.is_integer() else str(value)


def parse(segments: list[str], series_name: str, kind: str = "manga") -> ParsedName:
    """Parse a book from its path segments below the series folder + filename."""
    if not segments:
        return ParsedName(None, None, None, None, False, None)

    filename = _strip_ext(segments[-1])
    year_match = _YEAR.search(filename) if kind == "comic" else None
    year = int(year_match.group()) if year_match else None

    grouping = [_normalize(seg, series_name) for seg in segments[:-1]]
    cleaned = _normalize(filename, series_name)

    volume = next((v for seg in grouping if (v := _find_volume(seg)) is not None), None)
    if volume is None:
        volume = _find_volume(cleaned)

    number, number_sort = _find_number(cleaned)
    special, label = _find_special(cleaned)

    if special and number is None:
        # Base-less special (e.g. "Omake.cbz"): let the ordering pass place it.
        number = label
    return ParsedName(
        number=number,
        number_sort=number_sort,
        volume=volume,
        year=year,
        special=special,
        label=label,
    )
