"""Independent expected values for grouped/scalar catalog query implementations."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from src.catalog import repository
from src.catalog.models import Chapter, ProviderChapter
from src.progress.models import ProviderReadingProgress, ReadingProgress

from tests.support import make_series


@pytest.mark.parametrize("sort", ["recentlyAdded", "recentlyUpdated", "title", "rating", "unread"])
def test_catalog_statistics_and_cursor_matrix(db_session: Session, sort: str) -> None:
    base = datetime(2020, 1, 1, tzinfo=UTC)
    facts = []
    for index in range(12):
        count = index % 4
        work = make_series(
            db_session,
            title=f"Work {index % 5}",
            chapter_count=count,
            unread=count,
            rating=None if index % 3 == 0 else float(index % 4),
            favorite=bool(index % 2),
        )
        work.created_at = base + timedelta(days=index % 3)
        work.provider = "mangadex" if index % 3 != 0 else None
        chapters = list(
            db_session.scalars(
                select(Chapter).where(Chapter.series_id == work.id).order_by(Chapter.number_sort)
            )
        )
        local_dates, source_dates, read_numbers = [], [], []
        unread = count
        for number, chapter in enumerate(chapters):
            chapter.created_at = base + timedelta(days=10 + number)
            chapter.source_uploaded_at = (
                base + timedelta(days=30 + number) if number % 2 == 0 else None
            )
            chapter.provider_chapter_id = f"{index}-{number}"
            local_dates.append(chapter.created_at)
            if chapter.source_uploaded_at:
                source_dates.append(chapter.source_uploaded_at)
            # A partial local save contributes lastRead, but remains unread.
            if number == 0:
                db_session.add(
                    ReadingProgress(
                        chapter_id=chapter.id, series_id=work.id, completed=False, current_page=1
                    )
                )
                read_numbers.append(chapter.number_sort)
            if number == 1:
                # Multiple provider records for the same chapter must count once.
                for provider in ("mangadex", "other"):
                    db_session.add(
                        ProviderReadingProgress(
                            series_id=work.id,
                            provider=provider,
                            provider_chapter_id=chapter.provider_chapter_id,
                            completed=True,
                        )
                    )
                unread -= 1
        remote_date = base + timedelta(days=20 + index % 3)
        db_session.add(
            ProviderChapter(
                series_id=work.id,
                provider="mangadex",
                provider_chapter_id=f"remote-{index}",
                published_at=remote_date,
                last_seen_at=base,
            )
        )
        updated = (
            max(source_dates + [remote_date])
            if work.provider == "mangadex"
            else max(local_dates, default=work.created_at)
        )
        facts.append(
            {
                "id": work.id,
                "created": work.created_at.replace(tzinfo=None),
                "updated": updated.replace(tzinfo=None),
                "title": work.sort_title,
                "rating": work.rating if work.rating is not None else -1.0,
                "unread": unread,
                "count": count,
                "last": max(read_numbers, default=None),
                "progress": bool(count),
                "favorite": work.favorite,
            }
        )
    db_session.commit()
    sort_key = {"recentlyAdded": "created", "recentlyUpdated": "updated"}.get(sort, sort)
    for state, favorite in [
        (None, None),
        ("read", None),
        ("unread", None),
        ("in_progress", None),
        (None, True),
    ]:
        selected = [
            fact
            for fact in facts
            if (favorite is None or fact["favorite"] == favorite)
            and (state != "read" or fact["unread"] == 0)
            and (state not in {"unread", "in_progress"} or fact["unread"] > 0)
            and (state != "in_progress" or fact["progress"])
        ]
        expected = sorted(
            selected, key=lambda fact: (fact[sort_key], fact["id"]), reverse=sort != "title"
        )
        rows, cursor = [], None
        for _ in range(15):
            page, cursor = repository.list_series(
                db_session,
                repository.SeriesFilters(sort=sort, read_state=state, favorite=favorite),
                cursor=cursor,
                limit=2,
            )
            rows.extend(page)
            if cursor is None:
                break
        assert cursor is None
        assert [row.series.id for row in rows] == [fact["id"] for fact in expected]
        for row, fact in zip(rows, expected, strict=True):
            assert (row.chapter_count, row.unread_count, row.last_read, row.content_updated_at) == (
                fact["count"],
                fact["unread"],
                fact["last"],
                fact["updated"],
            )
        hydrated = repository.get_series_rows(db_session, [fact["id"] for fact in expected])
        assert {
            sid: (row.chapter_count, row.unread_count, row.content_updated_at)
            for sid, row in hydrated.items()
        } == {fact["id"]: (fact["count"], fact["unread"], fact["updated"]) for fact in expected}


def test_native_cursor_retains_selection_boundary_on_concurrent_delete(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    if db_session.get_bind().dialect.driver != "turso":
        pytest.skip("Only native grouping uses separate selection and hydration")
    from src.core.schema import decode_cursor

    first = make_series(db_session, title="A")
    make_series(db_session, title="B")
    db_session.commit()
    sid = first.id
    original = repository.get_series_rows

    def hydrate(session: Session, ids: list[str]):
        work = session.get(type(first), sid)
        assert work is not None
        session.delete(work)
        session.commit()
        return original(session, ids)

    monkeypatch.setattr(repository, "get_series_rows", hydrate)
    rows, cursor = repository.list_series(
        db_session, repository.SeriesFilters(sort="title"), limit=1
    )
    assert rows == []
    assert cursor is not None
    assert decode_cursor(cursor) == {"v": "a", "id": sid}


def test_catalog_index_upgrade_and_downgrade_preserve_data(db_engine, tmp_path) -> None:
    from pathlib import Path

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect
    from src.bootstrap import run_migrations
    from src.core.persistence.database import create_database_engine

    backend = Path(__file__).resolve().parents[1]
    scheme = "sqlite+turso" if db_engine.dialect.driver == "turso" else "sqlite"
    url = f"{scheme}:///{tmp_path / 'migration.db'}"
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "alembic"))
    config.attributes["database_url"] = url
    command.upgrade(config, "f3a82c65e190")
    engine = create_database_engine(url)
    try:
        with Session(engine) as session:
            work = make_series(session, title="Retained", chapter_count=2, unread=1)
            session.flush()
            sid = work.id
            session.commit()
        run_migrations(url)
        engine.dispose()
        with Session(engine) as session:
            row = repository.get_series(session, sid)
            assert row is not None
            assert (row.series.title, row.chapter_count, row.unread_count) == ("Retained", 2, 1)
        assert "ix_series_kind_added" in {
            index["name"] for index in inspect(engine).get_indexes("series")
        }
        command.downgrade(config, "f3a82c65e190")
        engine.dispose()
        assert "ix_series_kind_added" not in {
            index["name"] for index in inspect(engine).get_indexes("series")
        }
        with Session(engine) as session:
            row = repository.get_series(session, sid)
            assert row is not None
            assert (row.chapter_count, row.unread_count) == (2, 1)
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("source_year", "remote_year", "has_chapter", "expected_year"),
    [
        (None, None, False, 2020),
        (None, None, True, 2023),
        (None, 2021, True, 2021),
        (2024, None, True, 2024),
        (2025, 2024, True, 2025),
        (2024, 2025, True, 2025),
    ],
)
def test_publication_fallbacks(
    db_session: Session, source_year, remote_year, has_chapter, expected_year
) -> None:
    work = make_series(db_session, title="Publication", chapter_count=int(has_chapter))
    work.provider = "mangadex"
    work.created_at = datetime(2020, 1, 1, tzinfo=UTC)
    chapter = db_session.scalar(select(Chapter).where(Chapter.series_id == work.id))
    if chapter:
        chapter.created_at = datetime(2023, 1, 1, tzinfo=UTC)
        chapter.source_uploaded_at = (
            datetime(source_year, 1, 1, tzinfo=UTC) if source_year else None
        )
    db_session.add(
        ProviderChapter(
            series_id=work.id,
            provider="mangadex",
            provider_chapter_id="remote",
            published_at=datetime(remote_year, 1, 1, tzinfo=UTC) if remote_year else None,
            last_seen_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    db_session.commit()
    row = repository.get_series(db_session, work.id)
    assert row is not None
    assert row.content_updated_at.year == expected_year
    rows, _ = repository.list_series(db_session, repository.SeriesFilters(sort="recentlyUpdated"))
    assert rows[0].content_updated_at == row.content_updated_at
