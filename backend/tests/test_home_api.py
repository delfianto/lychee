"""Home exposes all eligible works, durable remote reads, and honest local discovery."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from src.catalog.models import Book, Chapter, ProviderChapter
from src.collections.models import Collection, CollectionSeries
from src.core.schema import encode_cursor
from src.progress.models import ProviderReadingProgress, ReadingProgress

from tests.support import make_series


def remote(session, series, number, *, language="en", published=None):
    series.provider = "mangadex"
    series.provider_series_id = f"remote-{series.id}"
    item = ProviderChapter(
        series_id=series.id,
        provider="mangadex",
        provider_chapter_id=f"{series.id}-{language}-{number}",
        number=str(number),
        number_sort=float(number),
        language=language,
        published_at=published or datetime(2026, 1, 1, tzinfo=UTC),
        last_seen_at=datetime.now(UTC),
    )
    session.add(item)
    session.flush()
    return item


def pages(client, shelf, **params):
    collected, cursor = [], None
    while True:
        response = client.get(
            f"/api/dashboard/{shelf}", params={**params, **({"cursor": cursor} if cursor else {})}
        )
        assert response.status_code == 200, response.text
        body = response.json()
        collected.extend(body["updates"] if shelf == "recentUpdates" else body["items"])
        cursor = body["nextCursor"]
        if cursor is None:
            return collected


def test_home_expands_shelves_and_pages_without_losing_tied_rows(
    client: TestClient, db_session: Session
):
    for index in range(31):
        series = make_series(
            db_session,
            title=f"Reading {index:02}",
            chapter_count=2,
            unread=1,
            library_status="reading",
        )
        series.created_at = datetime(2026, 1, 1, tzinfo=UTC)
        for progress in db_session.scalars(
            select(ReadingProgress).where(ReadingProgress.series_id == series.id)
        ):
            progress.updated_at = datetime(2026, 1, 1, tzinfo=UTC)
    db_session.commit()
    dashboard = client.get("/api/dashboard").json()
    for shelf in ("continueReading", "readingList", "recentlyAdded", "recentUpdates"):
        assert len(dashboard[shelf]) == 24
        assert dashboard["cursors"][shelf]
        all_items = pages(client, shelf, limit=7)
        expected = 62 if shelf == "recentUpdates" else 31
        assert len(all_items) == expected
        if shelf != "recentUpdates":
            assert len({item["id"] for item in all_items}) == expected
    assert [s["title"] for s in pages(client, "readingList")] == [
        f"Reading {i:02}" for i in range(31)
    ]


def test_continue_remote_progress_and_next_remote_after_local_completion(
    client: TestClient, db_session: Session
):
    series = make_series(db_session, title="Remote only")
    first, second = remote(db_session, series, 1), remote(db_session, series, 2)
    remote(db_session, series, 0, language="ja")
    db_session.add(
        ProviderReadingProgress(
            series_id=series.id,
            provider="mangadex",
            provider_chapter_id=first.provider_chapter_id,
            current_page=20,
            completed=True,
        )
    )
    local = make_series(db_session, title="Local done", chapter_count=1, unread=0)
    local_first, local_next = remote(db_session, local, 1), remote(db_session, local, 2)
    chapter = db_session.scalar(select(Chapter).where(Chapter.series_id == local.id))
    assert chapter is not None
    chapter.provider_chapter_id = local_first.provider_chapter_id
    db_session.commit()
    items = {s["id"]: s for s in client.get("/api/dashboard").json()["continueReading"]}
    assert items[series.id]["chapterCount"] == 0
    assert items[series.id]["resumeChapterId"] == f"adhoc:{series.id}:{second.provider_chapter_id}"
    assert (
        items[local.id]["resumeChapterId"] == f"adhoc:{local.id}:{local_next.provider_chapter_id}"
    )
    local.library_status = "dropped"
    db_session.commit()
    assert [s["id"] for s in pages(client, "continueReading")] == [series.id]
    db_session.add(
        ProviderReadingProgress(
            series_id=series.id,
            provider="mangadex",
            provider_chapter_id=second.provider_chapter_id,
            current_page=20,
            completed=True,
        )
    )
    db_session.commit()
    assert pages(client, "continueReading") == []


def test_continue_prefers_the_last_partially_read_chapter(client: TestClient, db_session: Session):
    series = make_series(db_session, title="Several unfinished", chapter_count=5, unread=5)
    chapters = list(
        db_session.scalars(
            select(Chapter).where(Chapter.series_id == series.id).order_by(Chapter.number_sort)
        )
    )
    for index in (2, 4):
        db_session.add(
            ReadingProgress(
                chapter_id=chapters[index].id,
                series_id=series.id,
                current_page=1,
                completed=False,
                updated_at=datetime(2026, 1, index + 1, tzinfo=UTC),
            )
        )
    db_session.commit()
    item = pages(client, "continueReading")[0]
    assert item["resumeChapterId"] == chapters[4].id
    assert item["resumeChapterLabel"] == "5"


def test_rediscovery_seeded_pagination_excludes_started_and_new(
    client: TestClient, db_session: Session
):
    old = datetime.now(UTC) - timedelta(days=60)
    expected = set()
    for index in range(29):
        item = make_series(db_session, title=f"Forgotten {index}")
        item.created_at = old
        expected.add(item.id)
    started = make_series(db_session, title="Started remotely")
    started.created_at = old
    first = remote(db_session, started, 1)
    db_session.add(
        ProviderReadingProgress(
            series_id=started.id,
            provider="mangadex",
            provider_chapter_id=first.provider_chapter_id,
            current_page=2,
        )
    )
    for status in ("completed", "dropped"):
        item = make_series(db_session, title=status, library_status=status)
        item.created_at = old
    make_series(db_session, title="Too new")
    comic = make_series(db_session, title="Old comic", kind="comic")
    comic.created_at = old
    gallery = make_series(db_session, title="Old gallery", kind="gallery")
    gallery.created_at = old
    short = make_series(
        db_session, title="Quick instead", status="completed", chapter_count=1, unread=1
    )
    short.created_at = old
    db_session.commit()
    first = pages(client, "rediscover", seed="day-one", limit=8)
    assert {s["id"] for s in first} == expected
    assert first == pages(client, "rediscover", seed="day-one", limit=8)
    assert [s["id"] for s in first] != [
        s["id"] for s in pages(client, "rediscover", seed="day-two", limit=8)
    ]
    assert [s["id"] for s in pages(client, "rediscover", discoveryKind="comic")] == [comic.id]
    body = client.get("/api/dashboard/rediscover", params={"seed": "day-one", "limit": 2}).json()
    assert (
        client.get(
            "/api/dashboard/rediscover", params={"seed": "day-two", "cursor": body["nextCursor"]}
        ).status_code
        == 400
    )


def test_quick_reads_require_local_pages_and_no_missing_chapters(
    client: TestClient, db_session: Session
):
    good = make_series(
        db_session, title="Short complete", status="completed", chapter_count=2, unread=2
    )
    for c in db_session.scalars(select(Chapter).where(Chapter.series_id == good.id)):
        c.page_count = 70
    oneshot = make_series(
        db_session, title="Oneshot", tag_ids=["oneshot"], chapter_count=1, unread=1
    )
    for label in (
        "Too long",
        "Unknown pages",
        "Deleted",
        "Not downloaded",
        "Incomplete cache",
        "Already read",
    ):
        s = make_series(
            db_session,
            title=label,
            status="completed",
            chapter_count=1,
            unread=0 if label == "Already read" else 1,
        )
        chapter = db_session.scalar(select(Chapter).where(Chapter.series_id == s.id))
        assert chapter is not None
        if label == "Too long":
            chapter.page_count = 201
        if label == "Unknown pages":
            chapter.page_count = 0
        if label == "Deleted":
            book = db_session.get(Book, chapter.book_id)
            assert book is not None
            book.deleted_at = datetime.now(UTC)
        if label == "Not downloaded":
            s.available_chapters = 1
        if label == "Incomplete cache":
            remote(db_session, s, 2)
    comic = make_series(
        db_session, title="Short comic", kind="comic", status="completed", chapter_count=1, unread=1
    )
    db_session.commit()
    found = {s["id"]: s for s in pages(client, "quickReads")}
    assert set(found) == {good.id, oneshot.id}
    assert found[good.id]["pageCount"] == 140 and found[oneshot.id]["pageCount"] == 1
    assert [s["id"] for s in pages(client, "quickReads", discoveryKind="comic")] == [comic.id]


def test_updates_publication_dates_deduplication_and_following(
    client: TestClient, db_session: Session
):
    followed = make_series(
        db_session, title="Following", library_status="reading", chapter_count=1, unread=1
    )
    favorite = make_series(db_session, title="Favorite", favorite=True)
    other = make_series(db_session, title="Other")
    first = remote(db_session, followed, 1, published=datetime(2026, 1, 1, tzinfo=UTC))
    chapter = db_session.scalar(select(Chapter).where(Chapter.series_id == followed.id))
    assert chapter is not None
    chapter.provider_chapter_id = first.provider_chapter_id
    # Legacy downloads can lack a source date; the cached feed supplies it.
    chapter.source_uploaded_at = None
    remote(db_session, followed, 2, published=datetime(2026, 2, 1, tzinfo=UTC))
    remote(db_session, favorite, 1, published=datetime(2026, 3, 1, tzinfo=UTC))
    remote(db_session, other, 1, published=datetime(2026, 4, 1, tzinfo=UTC))
    db_session.commit()
    scoped = pages(client, "recentUpdates", following=True, limit=1)
    assert [(s["series"]["id"], s["chapter"]) for s in scoped] == [
        (favorite.id, "1"),
        (followed.id, "2"),
        (followed.id, "1"),
    ]
    all_items = pages(client, "recentUpdates", limit=2)
    assert len(all_items) == 4 and all_items[0]["series"]["id"] == other.id
    assert (
        client.get("/api/dashboard", params={"following": True}).json()["recentUpdates"] == scoped
    )

    assert client.get("/api/updates").json()["items"][0]["updatedAt"].startswith("2026-01-01")
    book = db_session.get(Book, chapter.book_id)
    assert book is not None
    book.deleted_at = datetime.now(UTC)
    db_session.commit()
    assert pages(client, "recentUpdates", following=True) == scoped


def test_home_invalid_cursors_and_limits(client: TestClient):
    for shelf in (
        "continueReading",
        "recentUpdates",
        "rediscover",
        "quickReads",
        "readingList",
        "recentlyAdded",
    ):
        assert (
            client.get(f"/api/dashboard/{shelf}", params={"cursor": "garbage"}).status_code == 400
        )
        assert client.get(f"/api/dashboard/{shelf}", params={"limit": 0}).status_code == 422
    assert client.get("/api/dashboard/unknown").status_code == 422
    assert client.get("/api/dashboard", params={"discoveryKind": "gallery"}).status_code == 422
    for shelf, scope in [("continueReading", "continueReading"), ("recentUpdates", "updates:all")]:
        cursor = encode_cursor({"shelf": scope, "seed": "", "id": "last", "v": "invalid-date"})
        assert client.get(f"/api/dashboard/{shelf}", params={"cursor": cursor}).status_code == 400


def test_collection_filter_scoped_and_paginated(client: TestClient, db_session: Session):
    collection = Collection(name="Pinned", kind="manga")
    db_session.add(collection)
    db_session.flush()
    ids = set()
    for i in range(5):
        s = make_series(db_session, title=f"Listed {i}")
        ids.add(s.id)
        db_session.add(CollectionSeries(collection_id=collection.id, series_id=s.id, position=i))
    make_series(db_session, title="Outside")
    db_session.commit()
    gathered = []
    cursor = None
    while True:
        page = client.get(
            "/api/series",
            params={
                "collectionId": collection.id,
                "limit": 2,
                "sort": "title",
                **({"cursor": cursor} if cursor else {}),
            },
        ).json()
        gathered.extend(page["items"])
        cursor = page["nextCursor"]
        if not cursor:
            break
    assert {s["id"] for s in gathered} == ids


def test_recent_imports_get_discovery_beyond_the_newest_additions(
    client: TestClient, db_session: Session
):
    ids = []
    now = datetime.now(UTC)
    for index in range(52):
        series = make_series(db_session, title=f"New library {index}")
        series.created_at = now - timedelta(minutes=index)
        ids.append(series.id)
    db_session.commit()
    discovered = pages(client, "rediscover", seed="new-library")
    assert {s["id"] for s in discovered} == set(ids[24:])
    assert all(s["description"] is None for s in discovered)
