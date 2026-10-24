"""Portable title/alternative/credit search projection.

SQLite uses trigger-maintained FTS5 trigrams; optional local Turso uses native
Tantivy n-grams with a dirty-ID queue refreshed in the same write transaction.
Both are created/backfilled by Alembic and explicitly by isolated test fixtures.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, String, bindparam, text
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
    "CREATE TRIGGER IF NOT EXISTS series_fts_tv_move AFTER UPDATE OF series_id ON title_variant "
    "WHEN OLD.series_id != NEW.series_id "
    f"BEGIN {_REBUILD.format(sid='OLD.series_id')} END",
    "CREATE TRIGGER IF NOT EXISTS series_fts_sc_move AFTER UPDATE OF series_id ON series_credit "
    "WHEN OLD.series_id != NEW.series_id "
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
    "DROP TRIGGER IF EXISTS series_fts_tv_move",
    "DROP TRIGGER IF EXISTS series_fts_sc_move",
    "DROP TABLE IF EXISTS series_fts",
    "DROP TABLE IF EXISTS series_fts_dirty",
]


def create_search_index(connection: Connection) -> None:
    """Create the FTS table + triggers and backfill existing series (test/bootstrap
    path; the migration runs the same statements)."""
    statements = SEARCH_INDEX_STATEMENTS
    if connection.dialect.driver == "turso":
        # Keep the same trigger-maintained projection, with a native Tantivy
        # n-gram index instead of an unsupported FTS5 virtual table.
        statements = [
            "CREATE TABLE IF NOT EXISTS series_fts (series_id TEXT PRIMARY KEY, "
            "title TEXT NOT NULL, alt_titles TEXT NOT NULL, authors TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS series_fts_dirty (series_id TEXT PRIMARY KEY)",
            "CREATE INDEX IF NOT EXISTS series_fts_native ON series_fts "
            "USING fts (title, alt_titles, authors) "
            "WITH (tokenizer='ngram', weights='title=10.0,alt_titles=4.0,authors=1.0')",
        ]
        # Native FTS indexes cannot be rewritten twice by one firing statement.
        # Triggers record dirty IDs in a plain table; a pre-commit hook refreshes
        # the index with top-level SQL in the same transaction.
        for table, prefix, column in [
            ("series", "series", "id"),
            ("title_variant", "tv", "series_id"),
            ("series_credit", "sc", "series_id"),
        ]:
            for event_name, suffix in [("INSERT", "ai"), ("UPDATE", "au"), ("DELETE", "ad")]:
                refs = [f"OLD.{column}"] if event_name == "DELETE" else [f"NEW.{column}"]
                if event_name == "UPDATE":
                    refs.append(f"OLD.{column}")
                body = " ".join(
                    f"INSERT OR IGNORE INTO series_fts_dirty(series_id) VALUES ({ref});"
                    for ref in refs
                )
                statements.append(
                    f"CREATE TRIGGER IF NOT EXISTS series_fts_{prefix}_{suffix} "
                    f"AFTER {event_name} ON {table} BEGIN {body} END"
                )
        statements.append(SEARCH_INDEX_STATEMENTS[-1])
    for statement in statements[:-1]:
        connection.execute(text(statement))
    connection.execute(text("DELETE FROM series_fts"))
    connection.execute(text(statements[-1]))


_SEARCH_DIRTY_KEY = "lychee_search_dirty"
_SEARCH_SOURCE_TABLES = frozenset({"series", "title_variant", "series_credit", "library"})


def mark_turso_search(
    connection: Connection,
    _cursor: Any,
    statement: str,
    _parameters: Any,
    context: Any,
    _executemany: bool,
) -> None:
    """Skip index work for writes that cannot affect the searchable projection.

    Compiled ORM/Core DML identifies its target table reliably, including library
    deletes that cascade into series. Treat unstructured SQL conservatively:
    unknown writes/DDL may fire triggers, so keep the queue check for those.
    """
    if context.isinsert or context.isupdate or context.isdelete:
        compiled_statement = getattr(context.compiled, "statement", None)
        table = getattr(getattr(compiled_statement, "table", None), "name", None)
        if table is not None and table not in _SEARCH_SOURCE_TABLES:
            return
    elif statement.lstrip().upper().startswith(("SELECT", "PRAGMA", "EXPLAIN")):
        return
    connection.info[_SEARCH_DIRTY_KEY] = True


def reset_turso_search(connection: Connection) -> None:
    connection.info.pop(_SEARCH_DIRTY_KEY, None)


def sync_turso_search(connection: Connection) -> None:
    """Apply native index updates atomically before a Turso write commits."""
    if not connection.info.pop(_SEARCH_DIRTY_KEY, False):
        return
    raw = connection.connection.dbapi_connection
    if not getattr(raw, "in_transaction", False):
        return
    exists = connection.execute(
        text("SELECT 1 FROM sqlite_master WHERE name='series_fts_dirty' AND type='table'")
    ).first()
    if exists is None:
        return  # schema migrations before the search-index revision
    ids = connection.execute(text("SELECT series_id FROM series_fts_dirty")).scalars().all()
    for sid in ids:
        connection.execute(text("DELETE FROM series_fts WHERE series_id=:sid"), {"sid": sid})
        connection.execute(text(SEARCH_INDEX_STATEMENTS[-1] + " WHERE s.id=:sid"), {"sid": sid})
        connection.execute(text("DELETE FROM series_fts_dirty WHERE series_id=:sid"), {"sid": sid})
    # The top-level projection writes above are deliberately conservative raw
    # SQL and mark the connection too. They do not dirty source metadata again.
    reset_turso_search(connection)


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
    if session.get_bind().dialect.driver == "turso":
        sync_turso_search(session.connection())
    if not fts_available(session):
        return None
    match = build_match(q)
    if match is None:
        return None
    if session.get_bind().dialect.driver == "turso":
        # Tantivy uses backslash quoting, unlike FTS5's doubled double-quotes.
        terms = [term for term in q.split() if len(term) >= _MIN_TRIGRAM]
        match = " AND ".join(
            '"' + term.replace("\\", "\\\\").replace('"', '\\"') + '"' for term in terms
        )
        statement = (
            "SELECT series_id, fts_score(title,alt_titles,authors,:m) AS score "
            "FROM series_fts WHERE fts_match(title,alt_titles,authors,:m) "
            "ORDER BY score DESC LIMIT :lim"
        )
    else:
        statement = (
            "SELECT series_id FROM series_fts WHERE series_fts MATCH :m "
            "ORDER BY bm25(series_fts, 0.0, 10.0, 4.0, 1.0) LIMIT :lim"
        )
    query = text(statement)
    if session.get_bind().dialect.driver == "turso":
        # pyturso 0.8.3 matches bound FTS terms but returns zero relevance scores
        # for them. SQLAlchemy renders this value as an escaped SQL string literal
        # at execution time; never concatenate raw user input into the SQL.
        query = query.bindparams(bindparam("m", type_=String, literal_execute=True))
    rows = session.execute(query, {"m": match, "lim": limit}).all()
    return [row[0] for row in rows]
