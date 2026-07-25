"""Canonical taxonomy seed (MangaDex-aligned + lychee gallery extras).

Idempotent: only inserts rows whose id (slug) is absent, so user edits to
``name`` / ``enabled`` and user-created tags survive restarts. The exact MangaDex
set can be refreshed from ``/manga/tag`` via ``POST /api/taxonomy/refresh``; slugs
are stable.

The four ``genre|theme|content|format`` groups link to series via ``series_tag``.
``content_rating`` and ``demographic`` are fixed enum groups: ``system`` rows whose
ids are the values stored on ``Series.content_rating`` / ``Series.demographic``.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.taxonomy.models import Tag

# (slug, display name)
_GENRES = [
    ("action", "Action"),
    ("adventure", "Adventure"),
    ("boys-love", "Boys' Love"),
    ("comedy", "Comedy"),
    ("crime", "Crime"),
    ("drama", "Drama"),
    ("fantasy", "Fantasy"),
    ("girls-love", "Girls' Love"),
    ("historical", "Historical"),
    ("horror", "Horror"),
    ("isekai", "Isekai"),
    ("mecha", "Mecha"),
    ("medical", "Medical"),
    ("mystery", "Mystery"),
    ("philosophical", "Philosophical"),
    ("psychological", "Psychological"),
    ("romance", "Romance"),
    ("sci-fi", "Sci-Fi"),
    ("slice-of-life", "Slice of Life"),
    ("sports", "Sports"),
    ("superhero", "Superhero"),
    ("thriller", "Thriller"),
    ("tragedy", "Tragedy"),
    ("wuxia", "Wuxia"),
]
_THEMES = [
    ("aliens", "Aliens"),
    ("animals", "Animals"),
    ("cooking", "Cooking"),
    ("demons", "Demons"),
    ("harem", "Harem"),
    ("mafia", "Mafia"),
    ("magic", "Magic"),
    ("magical-girls", "Magical Girls"),
    ("martial-arts", "Martial Arts"),
    ("military", "Military"),
    ("monsters", "Monsters"),
    ("music", "Music"),
    ("ninja", "Ninja"),
    ("office-workers", "Office Workers"),
    ("police", "Police"),
    ("post-apocalyptic", "Post-Apocalyptic"),
    ("reincarnation", "Reincarnation"),
    ("reverse-harem", "Reverse Harem"),
    ("samurai", "Samurai"),
    ("school-life", "School Life"),
    ("supernatural", "Supernatural"),
    ("survival", "Survival"),
    ("time-travel", "Time Travel"),
    ("vampires", "Vampires"),
    ("video-games", "Video Games"),
    ("villainess", "Villainess"),
    ("virtual-reality", "Virtual Reality"),
    ("zombies", "Zombies"),
    # Gallery-oriented (art / fan-art / cosplay collections).
    ("illustration", "Illustration"),
    ("fan-art", "Fan Art"),
    ("cosplay", "Cosplay"),
    ("official", "Official"),
]
_FORMATS = [
    ("4-koma", "4-Koma"),
    ("adaptation", "Adaptation"),
    ("anthology", "Anthology"),
    ("award-winning", "Award Winning"),
    ("doujinshi", "Doujinshi"),
    ("fan-colored", "Fan Colored"),
    ("full-color", "Full Color"),
    ("long-strip", "Long Strip"),
    ("official-colored", "Official Colored"),
    ("oneshot", "Oneshot"),
    ("self-published", "Self-Published"),
    ("web-comic", "Web Comic"),
]
_CONTENT = [
    ("gore", "Gore"),
    ("sexual-violence", "Sexual Violence"),
]
# Fixed enum groups (system rows).
_CONTENT_RATINGS = [
    ("safe", "Safe"),
    ("suggestive", "Suggestive"),
    ("erotica", "Erotica"),
    ("mature", "Mature"),
]
_DEMOGRAPHICS = [
    ("shonen", "Shonen"),
    ("shojo", "Shojo"),
    ("seinen", "Seinen"),
    ("josei", "Josei"),
]


def _rows() -> Iterator[tuple[str, str, str, bool]]:
    """Yield (slug, name, group, system) for every seed row."""
    for group, items in (
        ("genre", _GENRES),
        ("theme", _THEMES),
        ("format", _FORMATS),
        ("content", _CONTENT),
    ):
        for slug, name in items:
            yield slug, name, group, False
    for slug, name in _CONTENT_RATINGS:
        yield slug, name, "content_rating", True
    for slug, name in _DEMOGRAPHICS:
        yield slug, name, "demographic", True


def seed_taxonomy(session: Session) -> int:
    """Insert any missing taxonomy rows. Returns the number added."""
    existing = set(session.scalars(select(Tag.id)).all())
    added = 0
    for slug, name, group, system in _rows():
        if slug in existing:
            continue
        session.add(Tag(id=slug, name=name, group=group, system=system, enabled=True))
        added += 1
    return added
