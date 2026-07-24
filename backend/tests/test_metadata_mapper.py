"""apply_metadata: mapping SeriesMetadata onto the Series model (locked fields, tags)."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from src.catalog.metadata import apply_metadata
from src.downloads.provider import SeriesMetadata
from src.taxonomy.models import Tag

from tests.support import make_series


def _meta(**over: object) -> SeriesMetadata:
    base: dict[str, object] = {
        "provider_series_id": "m1",
        "title": "Berserk",
        "alt_titles": [("ja", "ベルセルク")],
        "description": "A dark fantasy.",
        "status": "ongoing",
        "year": 1989,
        "content_rating": "suggestive",
        "demographic": "seinen",
        "original_language": "ja",
        "tags": [("Adventure", "genre"), ("Gore", "content")],
        "authors": ["Kentaro Miura"],
        "artists": ["Studio Gaga"],
        "cover_url": "https://uploads.mangadex.org/covers/m1/c.jpg.512.jpg",
        "total_chapters": 364,
        "community_rating": 8.4,
        "external_ids": {"mal": "2"},
    }
    base.update(over)
    return SeriesMetadata(**base)  # type: ignore[arg-type]


def test_apply_metadata_maps_all_fields(db_session: Session) -> None:
    series = make_series(db_session, title="berserk-folder", kind="manga")
    db_session.commit()

    apply_metadata(db_session, series, _meta(), fetch_covers=True)
    db_session.commit()

    assert series.title == "Berserk"
    assert series.sort_title == "berserk"
    assert series.description == "A dark fantasy."
    assert series.year == 1989
    assert series.status == "ongoing"
    assert series.content_rating == "suggestive"
    assert series.demographic == "seinen"
    assert series.origin_country == "jp"
    assert series.rating == 8.4
    assert series.total_chapters == 364
    assert series.cover_source == "https://uploads.mangadex.org/covers/m1/c.jpg.512.jpg"
    assert series.external_ids_json == {"mal": "2"}
    assert {(c.name, c.role) for c in series.credits} == {
        ("Kentaro Miura", "author"),
        ("Studio Gaga", "artist"),
    }
    assert {t.name for t in series.tags} == {"Adventure", "Gore"}
    assert any(v.is_primary and v.title == "Berserk" for v in series.title_variants)
    assert any(v.title == "ベルセルク" for v in series.title_variants)


def test_apply_metadata_respects_locked_fields(db_session: Session) -> None:
    series = make_series(db_session, title="Keep Me", kind="manga")
    series.locked_fields_json = ["title", "description"]
    db_session.commit()

    apply_metadata(db_session, series, _meta(title="New", description="new"), fetch_covers=True)
    db_session.commit()

    assert series.title == "Keep Me"  # locked
    assert series.description != "new"  # locked
    assert series.year == 1989  # unlocked → applied


def test_apply_metadata_skips_cover_when_fetch_covers_off(db_session: Session) -> None:
    series = make_series(db_session, title="X", kind="manga")
    db_session.commit()
    apply_metadata(db_session, series, _meta(), fetch_covers=False)
    db_session.commit()
    assert series.cover_source is None


def test_apply_metadata_reuses_existing_tag(db_session: Session) -> None:
    existing = db_session.scalars(select(Tag)).first()
    assert existing is not None  # taxonomy is seeded
    before = db_session.scalar(select(func.count()).select_from(Tag))

    series = make_series(db_session, title="X", kind="manga")
    db_session.commit()
    apply_metadata(
        db_session, series, _meta(tags=[(existing.name, existing.group)]), fetch_covers=True
    )
    db_session.commit()

    assert existing.id in [t.id for t in series.tags]  # matched an existing taxonomy row
    assert db_session.scalar(select(func.count()).select_from(Tag)) == before  # no new tag
