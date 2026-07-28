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

from src.taxonomy.models import Tag, TagAlias
from src.taxonomy.slug import slugify

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
# Fixed enum groups (system rows). The top tier forks by kind: MangaDex-synced
# manga/comic use MangaDex's own term verbatim ("pornographic"); galleries never
# sync with MangaDex, so they get their own top tier ("explicit") instead of
# borrowing MangaDex's word for it. See notes/decisions/10-tagging-content-rating.md.
_CONTENT_RATINGS = [
    ("safe", "Safe"),
    ("suggestive", "Suggestive"),
    ("erotica", "Erotica"),
    ("pornographic", "Pornographic"),
    ("explicit", "Explicit"),
]
_DEMOGRAPHICS = [
    ("shonen", "Shōnen"),
    ("shojo", "Shōjo"),
    ("seinen", "Seinen"),
    ("josei", "Josei"),
]
# Free-text synonyms that resolve to a canonical tag above (see
# notes/decisions/21-tag-aliases.md) — colloquial slang and abbreviations. MangaDex's own
# raw contentRating value ("pornographic") needs no alias any more: it slugifies
# straight to the canonical tag id (see notes/decisions/21-tag-aliases.md).
# (display name, canonical tag id)
_ALIASES = [
    ("Ecchi", "suggestive"),
    ("Hentai", "pornographic"),
    ("NSFW", "pornographic"),
    ("Yaoi", "boys-love"),
    ("BL", "boys-love"),
    ("Yuri", "girls-love"),
    ("GL", "girls-love"),
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
    """Insert any missing taxonomy rows (tags, then aliases). Returns the number added."""
    existing = set(session.scalars(select(Tag.id)).all())
    added = 0
    for slug, name, group, system in _rows():
        if slug in existing:
            continue
        session.add(Tag(id=slug, name=name, group=group, system=system, enabled=True))
        existing.add(slug)
        added += 1

    existing_aliases = set(session.scalars(select(TagAlias.id)).all())
    for name, tag_id in _ALIASES:
        slug = slugify(name)
        if slug in existing_aliases or slug in existing:
            continue
        session.add(TagAlias(id=slug, name=name, tag_id=tag_id))
        existing_aliases.add(slug)
        added += 1
    return added
