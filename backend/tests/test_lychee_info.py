"""lychee.info sidecar: schema/parser validation + apply_lychee_info mapping (notes/decisions/20-lychee-info-metadata.md)."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session
from src.catalog.service import apply_lychee_info
from src.downloads.provider import MangaMatch, RemoteChapter, SeriesMetadata, register_provider
from src.ingest.lychee_info import LycheeInfoParseError, parse_lychee_info
from src.tasks.queue import queue
from src.taxonomy.models import Tag

from tests.support import make_series

# --- parser / schema validation -------------------------------------------------


def test_parse_valid_file() -> None:
    raw = """
schema: 1
kind: manga
title: "Bloodmoon Apothecary"
titles:
  - lang: ja
    type: native
    title: "血月の薬局"
description: "A dark tale."
status: ongoing
year: 2023
originCountry: kr
contentRating: suggestive
demographic: shonen
tags:
  genre: [horror, medical]
  format: [doujinshi]
credits:
  - name: "Ha-eun Park"
    role: author
crossovers:
  - series: "Some Existing Series"
    characters: [Character A]
provider:
  mangadex: "abc123"
external:
  anilist: "999"
generated:
  by: lychee-mcp
  version: 1
"""
    info = parse_lychee_info(raw.encode())
    assert info.title == "Bloodmoon Apothecary"
    assert info.content_rating == "suggestive"
    assert info.demographic == "shonen"
    assert info.tags is not None and info.tags.genre == ["horror", "medical"]
    assert info.credits is not None and info.credits[0].name == "Ha-eun Park"
    assert info.crossovers is not None and info.crossovers[0].series == "Some Existing Series"
    assert info.provider == {"mangadex": "abc123"}
    assert info.external == {"anilist": "999"}
    assert info.generated is not None and info.generated.version == 1


def test_parse_rejects_bad_yaml() -> None:
    with pytest.raises(LycheeInfoParseError):
        _ = parse_lychee_info(b"{not: valid: yaml")


def test_parse_rejects_non_mapping() -> None:
    with pytest.raises(LycheeInfoParseError):
        _ = parse_lychee_info(b"- just\n- a\n- list\n")


def test_parse_rejects_hallucinated_field() -> None:
    with pytest.raises(LycheeInfoParseError, match="fooBar"):
        _ = parse_lychee_info(b"schema: 1\nkind: manga\nfooBar: 1\n")


def test_parse_rejects_bad_enum() -> None:
    with pytest.raises(LycheeInfoParseError):
        _ = parse_lychee_info(b"schema: 1\nkind: webtoon\n")


def test_parse_rejects_unsupported_schema_version() -> None:
    with pytest.raises(LycheeInfoParseError, match="schema version"):
        _ = parse_lychee_info(b"schema: 2\nkind: manga\n")


def test_parse_every_field_optional_except_schema_and_kind() -> None:
    info = parse_lychee_info(b"schema: 1\nkind: gallery\n")
    assert info.title is None
    assert info.tags is None
    assert info.credits is None


# --- apply_lychee_info -----------------------------------------------------------


def _info(yaml_text: str):
    return parse_lychee_info(yaml_text.encode())


def test_apply_sets_and_locks_scalar_fields(db_session: Session) -> None:
    series = make_series(db_session, title="folder-name", kind="manga")
    db_session.commit()

    info = _info("""
schema: 1
kind: manga
title: "Real Title"
description: "desc"
year: 2020
status: completed
contentRating: pornographic
demographic: seinen
originCountry: jp
""")
    warnings = apply_lychee_info(db_session, series, info)
    db_session.commit()

    assert warnings == []
    assert series.title == "Real Title"
    assert series.description == "desc"
    assert series.year == 2020
    assert series.status == "completed"
    assert series.content_rating == "pornographic"
    assert series.demographic == "seinen"
    assert series.origin_country == "jp"
    locked = set(series.locked_fields_json or [])
    assert {"title", "description", "year", "status", "content_rating", "demographic"} <= locked


def test_apply_is_partial_only_touches_given_fields(db_session: Session) -> None:
    series = make_series(db_session, title="Existing Title", kind="manga", year=1999)
    db_session.commit()

    info = _info("""
schema: 1
kind: manga
tags:
  genre: [horror]
""")
    _ = apply_lychee_info(db_session, series, info)
    db_session.commit()

    assert series.title == "Existing Title"  # untouched
    assert series.year == 1999  # untouched
    assert "title" not in set(series.locked_fields_json or [])


def test_apply_creates_and_unions_tags(db_session: Session) -> None:
    series = make_series(db_session, title="Series A", kind="manga")
    existing = Tag(id="already-there", name="Already There", group="genre")
    db_session.add(existing)
    db_session.flush()
    series.tags = [existing]
    db_session.commit()

    info = _info("""
schema: 1
kind: manga
tags:
  genre: [Horror]
  format: [Doujinshi]
""")
    _ = apply_lychee_info(db_session, series, info)
    db_session.commit()

    names = {t.name for t in series.tags}
    assert names == {"Already There", "Horror", "Doujinshi"}  # union, not replace
    created = db_session.get(Tag, "horror")
    assert created is not None and created.group == "genre" and not created.system


def test_apply_titles_union_merge_no_lock(db_session: Session) -> None:
    series = make_series(db_session, title="Series A", kind="manga")
    db_session.commit()

    info = _info("""
schema: 1
kind: manga
titles:
  - lang: ja
    type: native
    title: "Native Title"
""")
    _ = apply_lychee_info(db_session, series, info)
    db_session.commit()

    assert [(v.language, v.title, v.variant_type) for v in series.title_variants] == [
        ("ja", "Native Title", "native")
    ]
    assert "title" not in set(series.locked_fields_json or [])  # additive, never locks

    # Re-applying the identical variant doesn't duplicate it.
    _ = apply_lychee_info(db_session, series, info)
    db_session.commit()
    assert len(series.title_variants) == 1


def test_apply_credits_split_by_role_partial(db_session: Session) -> None:
    series = make_series(db_session, title="Series A", kind="manga", authors=[], artists=[])
    db_session.commit()

    info = _info("""
schema: 1
kind: manga
credits:
  - name: "Artist Only"
    role: artist
""")
    _ = apply_lychee_info(db_session, series, info)
    db_session.commit()

    assert [c.name for c in series.credits if c.role == "artist"] == ["Artist Only"]
    assert [c.name for c in series.credits if c.role == "author"] == []


def test_apply_crossover_maps_source_and_characters(db_session: Session) -> None:
    series = make_series(db_session, title="Gallery A", kind="gallery")
    db_session.commit()

    info = _info("""
schema: 1
kind: gallery
crossovers:
  - series: "Some Franchise"
    characters: [Alice, Bob]
""")
    warnings = apply_lychee_info(db_session, series, info)
    db_session.commit()

    assert series.source == "Some Franchise"
    assert series.characters_json == ["Alice", "Bob"]
    assert warnings == []


def test_apply_multiple_crossovers_warns_and_applies_first_only(db_session: Session) -> None:
    series = make_series(db_session, title="Gallery A", kind="gallery")
    db_session.commit()

    info = _info("""
schema: 1
kind: gallery
crossovers:
  - series: "First Franchise"
    characters: [Alice]
  - series: "Second Franchise"
    characters: [Carol]
""")
    warnings = apply_lychee_info(db_session, series, info)

    assert series.source == "First Franchise"
    assert series.characters_json == ["Alice"]
    assert any("only the first" in w for w in warnings)


def test_apply_kind_mismatch_warns_and_ignores_kind_but_applies_rest(db_session: Session) -> None:
    series = make_series(db_session, title="Series A", kind="manga")
    db_session.commit()

    info = _info("""
schema: 1
kind: gallery
title: "New Title"
""")
    warnings = apply_lychee_info(db_session, series, info)

    assert series.kind == "manga"  # never reclassified
    assert series.title == "New Title"  # everything else still applied
    assert any("kind" in w for w in warnings)


def test_apply_kind_inapplicable_fields_warn_and_are_skipped(db_session: Session) -> None:
    series = make_series(db_session, title="Gallery A", kind="gallery", status="ongoing")
    db_session.commit()

    info = _info("""
schema: 1
kind: gallery
status: completed
demographic: shonen
""")
    warnings = apply_lychee_info(db_session, series, info)

    assert series.status == "ongoing"  # ignored
    assert series.demographic == "none"  # ignored (default from make_series)
    assert len(warnings) == 2


def test_apply_external_ids_merge_by_known_tracker_key(db_session: Session) -> None:
    series = make_series(db_session, title="Series A", kind="manga")
    series.external_ids_json = {"mal": "existing"}
    db_session.commit()

    info = _info("""
schema: 1
kind: manga
external:
  anilist: "555"
  unknownTracker: "x"
""")
    warnings = apply_lychee_info(db_session, series, info)

    assert series.external_ids_json == {"mal": "existing", "al": "555"}
    assert any("unknownTracker" in w for w in warnings)


def test_apply_provider_seeds_match_and_triggers_refresh(client, db_session: Session) -> None:
    register_provider(_FakeMangaDex())
    series = make_series(db_session, title="Series A", kind="manga")
    db_session.commit()

    info = _info("""
schema: 1
kind: manga
provider:
  mangadex: "md-123"
""")
    warnings = apply_lychee_info(db_session, series, info)
    queue.wait_idle(timeout=30.0)

    assert warnings == []
    assert series.provider == "mangadex"
    assert series.provider_series_id == "md-123"


def test_apply_provider_unavailable_warns(db_session: Session) -> None:
    series = make_series(db_session, title="Series A", kind="manga")
    db_session.commit()

    info = _info("""
schema: 1
kind: manga
provider:
  notaprovider: "x"
""")
    warnings = apply_lychee_info(db_session, series, info)

    assert series.provider is None
    assert any("notaprovider" in w for w in warnings)


class _FakeMangaDex:
    id = "mangadex"

    def list_chapters(
        self, provider_series_id: str, *, language: str = "en"
    ) -> list[RemoteChapter]:
        return []

    def fetch_pages(self, chapter, *, data_saver: bool = False, on_page=None) -> list[bytes]:
        return []

    def search(self, title: str, *, limit: int = 5) -> list[MangaMatch]:
        return []

    def get_metadata(self, provider_series_id: str, *, language: str = "en") -> SeriesMetadata:
        return SeriesMetadata(provider_series_id=provider_series_id, title="Matched Title")

    def list_new_chapters(
        self, provider_series_id: str, *, known: set[str], language: str = "en"
    ) -> list[RemoteChapter]:
        return []
