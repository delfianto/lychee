# 02 — Backend: Python 3.14 + FastAPI + SQLAlchemy + Alembic

**Status:** Implemented.

## Stack

- **Runtime:** Python 3.14, managed by `uv`.
- **Framework:** FastAPI (async), served by `uvicorn`.
- **Persistence:** SQLAlchemy 2.0 (**sync** ORM, not async — the slow path
  here is media/scan I/O, not DB access) + Alembic migrations, SQLite
  ([04](04-database-sqlite.md)).
- **Validation:** Pydantic v2 / pydantic-settings.
- **Logging:** `structlog` (console dev / JSON prod, `LOG_FORMAT`).
- **Quality gate:** ruff (lint + format), basedpyright — **`standard` mode**,
  not strict — pytest.
- **API:** REST at `/api` (no version segment, no `/v1`). No OPDS
  ([15](15-api-surface.md) — explicitly out of scope). SSE (`/api/events`)
  for live scan/download/task progress.

Explicitly **not** present, on purpose: no auth/session layer (single
implicit "default" user, [12](12-auth-users.md)), no OPDS, no async DB
driver.

## Architecture — vertical slices, not horizontal layers

Each subpackage under `backend/src/` is a domain module, self-contained end
to end: `router.py` (parse/validate, call service, return schema) →
`service.py` (business logic, raises `LycheeError`, HTTP-agnostic) →
`repository.py` (SQLAlchemy queries, only in modules with nontrivial query
logic) + `models.py` (ORM) + `schema.py` (Pydantic request/response,
singular — not `schemas.py`) + `deps.py` (FastAPI DI, where needed). Current
domains: `catalog` (series/chapters/books — the biggest), `library`,
`collections`, `progress`, `taxonomy`, `tasks`, `downloads`, `integrations`,
`providers` (MangaDex client), `trackers` (AniList/MyAnimeList/MangaUpdates),
`ingest` (scan/parse/import), `media` (AVIF encode, thumbnails, container
handling, render cache), `fs` (server-side path browser), `core`, `health`.

**Routers never raise `HTTPException` and never touch the ORM directly.**
Services raise `LycheeError` subclasses (`core/exceptions.py`); one handler
in `main.py` maps each to its HTTP status. Every error response has the shape
`{"error": {"code", "message"}}`, including framework 404/405/422. API
schemas are camelCase-on-wire via `CamelModel` (`core/schema.py`). IDs are
12-char nanoids (`gen_id()`). List endpoints return `Page[T]` (cursor-based)
or `OffsetPage[T]` (page/total — used only for the taxonomy admin table).

## Media libraries actually in use

Not the broad format-coverage list originally scoped — CBZ/ZIP + image
directories cover the common case, and RAR/7z/PDF/EPUB were decided
**not planned** ([media/containers.py](../../backend/src/media/containers.py)'s
own module docstring says so directly):

- Archives: stdlib `zipfile` only.
- Images: `Pillow` only (native AVIF via bundled libavif) — no `pyvips`, no
  `pillow-heif`.
- Container-kind detection: fixed extension map, not `python-magic`
  content-sniffing.
- Natural sort: a hand-rolled regex (`natural_key()` in `media/containers.py`),
  not `natsort`.
- Fast hashing: `xxhash` (`xxh3_128`) — this one was pinned as planned, used
  for move/restore detection during scans.

## Background jobs

A plain in-process `ThreadPoolExecutor` queue (`tasks/queue.py`), not a
persisted SQLite task table or APScheduler — see [08](08-task-runner.md) for
what actually shipped there and why.

## Why this stack over the alternatives researched

FastAPI + SQLAlchemy + Alembic covers async where it pays (page/event
streaming) without forcing async everywhere, with a mature migration story
SQLite needs. The Kotlin/Spring Boot, Crystal/Kemal, and C#/LiteDB stacks
considered from comparable scan-and-index servers were all passed over for
being either heavier than a solo self-hosted project needs, or (LiteDB)
lacking real migration tooling.
