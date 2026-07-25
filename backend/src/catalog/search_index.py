"""SQLite FTS5 full-text search index over series title / alt-titles / authors.

`series_fts` is a standalone own-content FTS5 virtual table with the **trigram**
tokenizer, which gives substring + typo-tolerant matching and bm25 ranking. The
series primary key is a 12-char nanoid (FTS5 rowids are integers), so it is
stored as an ``UNINDEXED`` column and used to map matches back to catalog rows.

The index is kept in sync entirely by **SQLite triggers** on the source tables
(`series`, `title_variant`, `series_credit`): every insert/update/delete rebuilds
the affected series' FTS row by re-aggregating its variants and credits. This
covers every write path (scanner, provider import, metadata apply, seeding) with
no application hooks, and the ``EXISTS``-guarded rebuild leaves no orphan row when
a series is cascade-deleted.

The DDL constants here are the single source of truth: the Alembic migration runs
them against the real database, and the test harness runs them after
``create_all`` (which doesn't know about virtual tables or triggers).
"""

from __future__ import annotations

from sqlalchemy import Connection, text
from sqlalchemy.orm import Session

_FTS_PREFIX = "series_fts"
_MIN_TRIGRAM = 3  # the trigram tokenizer needs ≥3 chars to emit a token

# Rebuild one series' FTS row from its current title + aggregated variants/credits.
# Guarded by the series row still existing, so a cascade delete leaves no orphan.
_REBUILD = """
  DELETE FROM series_fts WHERE series_id = {sid};
  INSERT INTO series_fts(series_id, title, alt_titles, authors)
  SELECT s.id, s.title,
    (SELECT COALESCE(group_concat(tv.title, ' '), '') FROM title_variant tv WHERE tv.series_id = s.id),
    (SELECT COALESCE(group_concat(sc.name, ' '), '') FROM series_credit sc WHERE sc.series_id = s.id)
  FROM series s WHERE s.id = {sid};
"""

# Order: table, then triggers, then a one-time backfill of pre-existing series.
SEARCH_INDEX_STATEMENTS: list[str] = [
    "CREATE VIRTUAL TABLE IF NOT EXISTS series_fts "
    "USING fts5(series_id UNINDEXED, title, alt_titles, authors, tokenize = 'trigram')",
    f"CREATE TRIGGER IF NOT EXISTS series_fts_series_ai AFTER INSERT ON series "
    f"BEGIN {_REBUILD.format(sid='NEW.id')} END",
    f"CREATE TRIGGER IF NOT EXISTS series_fts_series_au AFTER UPDATE ON series "
    f"BEGIN {_REBUILD.format(sid='NEW.id')} END",
    "CREATE TRIGGER IF NOT EXISTS series_fts_series_ad AFTER DELETE ON series "
    "BEGIN DELETE FROM series_fts WHERE series_id = OLD.id; END",
    f"CREATE TRIGGER IF NOT EXISTS series_fts_tv_ai AFTER INSERT ON title_variant "
    f"BEGIN {_REBUILD.format(sid='NEW.series_id')} END",
    f"CREATE TRIGGER IF NOT EXISTS series_fts_tv_au AFTER UPDATE ON title_variant "
    f"BEGIN {_REBUILD.format(sid='NEW.series_id')} END",
    f"CREATE TRIGGER IF NOT EXISTS series_fts_tv_ad AFTER DELETE ON title_variant "
    f"BEGIN {_REBUILD.format(sid='OLD.series_id')} END",
    f"CREATE TRIGGER IF NOT EXISTS series_fts_sc_ai AFTER INSERT ON series_credit "
    f"BEGIN {_REBUILD.format(sid='NEW.series_id')} END",
    f"CREATE TRIGGER IF NOT EXISTS series_fts_sc_au AFTER UPDATE ON series_credit "
    f"BEGIN {_REBUILD.format(sid='NEW.series_id')} END",
    f"CREATE TRIGGER IF NOT EXISTS series_fts_sc_ad AFTER DELETE ON series_credit "
    f"BEGIN {_REBUILD.format(sid='OLD.series_id')} END",
    "INSERT INTO series_fts(series_id, title, alt_titles, authors) "
    "SELECT s.id, s.title, "
    "  (SELECT COALESCE(group_concat(tv.title, ' '), '') FROM title_variant tv WHERE tv.series_id = s.id), "
    "  (SELECT COALESCE(group_concat(sc.name, ' '), '') FROM series_credit sc WHERE sc.series_id = s.id) "
    "FROM series s",
]

SEARCH_INDEX_DROP_STATEMENTS: list[str] = [
    "DROP TRIGGER IF EXISTS series_fts_series_ai",
    "DROP TRIGGER IF EXISTS series_fts_series_au",
    "DROP TRIGGER IF EXISTS series_fts_series_ad",
    "DROP TRIGGER IF EXISTS series_fts_tv_ai",
    "DROP TRIGGER IF EXISTS series_fts_tv_au",
    "DROP TRIGGER IF EXISTS series_fts_tv_ad",
    "DROP TRIGGER IF EXISTS series_fts_sc_ai",
    "DROP TRIGGER IF EXISTS series_fts_sc_au",
    "DROP TRIGGER IF EXISTS series_fts_sc_ad",
    "DROP TABLE IF EXISTS series_fts",
]


def create_search_index(connection: Connection) -> None:
    """Create the FTS table + triggers and backfill existing series (test/bootstrap
    path; the migration runs the same statements)."""
    for statement in SEARCH_INDEX_STATEMENTS:
        _ = connection.execute(text(statement))


def drop_search_index(connection: Connection) -> None:
    for statement in SEARCH_INDEX_DROP_STATEMENTS:
        _ = connection.execute(text(statement))


def fts_available(session: Session) -> bool:
    """Whether the FTS table exists (it may not if migrations haven't been run)."""
    row = session.execute(
        text("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = :n"),
        {"n": _FTS_PREFIX},
    ).first()
    return row is not None


def build_match(q: str) -> str | None:
    """Build an FTS5 MATCH expression, or None if the query can't drive FTS.

    Each whitespace-separated term of ≥3 chars becomes a quoted (operator-safe)
    trigram substring; the terms are AND-ed. Shorter terms (including 1–2 char CJK
    queries) yield no trigrams, so if nothing usable remains we return None and let
    the caller fall back to LIKE.
    """
    terms = [t for t in q.split() if len(t) >= _MIN_TRIGRAM]
    if not terms:
        return None
    return " AND ".join('"' + t.replace('"', '""') + '"' for t in terms)


def search_ids(session: Session, q: str, *, limit: int = 20) -> list[str] | None:
    """Series ids for ``q`` ranked best-first, or None if FTS can't serve the query
    (unavailable, or too short) so the caller falls back to LIKE. Title matches are
    weighted above alt-titles above authors via bm25 column weights."""
    if not fts_available(session):
        return None
    match = build_match(q)
    if match is None:
        return None
    rows = session.execute(
        text(
            "SELECT series_id FROM series_fts WHERE series_fts MATCH :m "
            "ORDER BY bm25(series_fts, 0.0, 10.0, 4.0, 1.0) LIMIT :lim"
        ),
        {"m": match, "lim": limit},
    ).all()
    return [row[0] for row in rows]
