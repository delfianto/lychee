# backend/ — lychee API

FastAPI service for lychee, a self-hosted manga/comic/ebook media server. See the
[repo-root AGENTS.md](../AGENTS.md) for the monorepo overview; this file covers
`backend/` specifically.

## Stack

- **Runtime:** Python 3.14, managed by [`uv`](https://docs.astral.sh/uv/) (`backend/.venv`).
- **Framework:** FastAPI (async), served by `uvicorn`.
- **Persistence:** SQLAlchemy 2.0 (sync ORM) + Alembic migrations, SQLite (WAL mode).
- **Validation:** Pydantic v2 / pydantic-settings.
- **Logging:** `structlog` (console renderer in dev, JSON in production — `LOG_FORMAT`).
- **Quality gate:** ruff (lint + format), basedpyright (`standard` mode), pytest.

Not present, on purpose — don't assume otherwise: no auth/session layer (single
implicit "default" user, see [ADR 12](../notes/decisions/12-auth-users.md)), no OPDS
(explicitly out of scope, [ADR 15](../notes/decisions/15-api-surface.md)), no async DB
driver (SQLAlchemy is used synchronously — the slow path here is media/scan I/O, not
DB access).

## Layout — vertical slices, not horizontal layers

Each subpackage under `src/` is a **domain module**, self-contained end to end:

```
src/<domain>/
  router.py      # FastAPI routes — parse/validate params, call service, return schema
  service.py      # business logic, orchestration; HTTP-agnostic (raises LycheeError)
  repository.py   # SQLAlchemy queries (only in modules with nontrivial query logic)
  models.py       # SQLAlchemy ORM models for this domain
  schema.py        # Pydantic request/response models (CamelModel-based)
  deps.py          # FastAPI dependencies (DI) specific to this domain
```

Not every module has every file — small ones (e.g. `health/`) are just a router;
others fold repository logic into `service.py` when there's little to it. Current
domains: `catalog` (series/chapters/books — the biggest module), `library`,
`collections`, `progress`, `taxonomy` (tags/ratings), `tasks` (background job
queue + SSE), `downloads` (chapter download queue), `integrations` (providers +
trackers wiring, local import), `providers` (MangaDex client), `trackers`
(AniList/MyAnimeList/MangaUpdates), `ingest` (filesystem scan/parse/import),
`media` (AVIF encode, thumbnails, video/container probing, render cache), `fs`
(server-side path browser for the "add library" UI), `core` (config, DB engine,
logging, shared exceptions/schema), `health`.

`src/models.py` is **not** a domain module — it's an aggregation point that imports
every ORM model so `Base.metadata` is complete for Alembic autogenerate and app
startup. Feature code imports models from its own domain; only import this module
where the *whole* schema must be registered (migrations, test fixtures).

`src/main.py` wires the FastAPI app: registers every router, the lifespan hook
(bootstrap, provider/tracker registration), CORS, and the three global exception
handlers that translate errors to the standard response shape (see below).

## Conventions

**Routers never raise `HTTPException` and never talk to the ORM directly.** Routes
parse/validate input, delegate to `service.py`, and return a schema. Services raise
`LycheeError` subclasses (`src/core/exceptions.py`: `BadRequestError`,
`NotFoundError`, `ConflictError`, `ValidationError`); a single handler in
`main.py` maps each to its HTTP status. This keeps the service layer HTTP-agnostic
and testable without a client. Every error response has the shape
`{"error": {"code": <slug>, "message": <text>}}` — this includes framework errors
(404 route-not-found, 405, 422 validation) via handlers on `StarletteHTTPException`
and `RequestValidationError`, not just domain errors.

**API schemas are camelCase on the wire, snake_case in Python.** Every
request/response model subclasses `CamelModel` (`src/core/schema.py`): an
alias generator converts `field_name` → `fieldName` on serialization, and
`populate_by_name=True` accepts either casing on input. Don't hand-roll
`alias=` on individual fields. Datetimes use the `UtcDatetime` annotated type so
naive SQLite timestamps always serialize with an explicit UTC offset. List
endpoints return `Page[T]` (cursor-based, via `encode_cursor`/`decode_cursor` —
used for grids/feeds/infinite scroll) or `OffsetPage[T]` (page/total, used for the
one admin-style table: taxonomy).

**Models:** most tables use `BaseModel` (`src/core/persistence/base_model.py`) — a
12-char nanoid `id` + `created_at`/`updated_at`. Entities with a natural key
(e.g. slugs) use the bare `TimestampMixin` instead.

**IDs are nanoid, not UUID or autoincrement** — `gen_id()` in `base_model.py`.

**FastAPI dependency injection:** `DbSession = Annotated[Session, Depends(get_db)]`
(`src/core/persistence/database.py`) is the standard param type for a request-scoped
session; domain `deps.py` modules define more (e.g. `catalog/deps.py` for the
thumbnail store / render cache), overridden in tests via
`app.dependency_overrides`.

**Background work** (`src/tasks/queue.py`) runs on a small `ThreadPoolExecutor`
(one worker by default — SQLite has one writer, so more workers wouldn't help
write throughput), each job getting its own DB session via a `sessionmaker`
handed to `queue.configure()`. A route validates, calls `queue.submit(...)`,
and returns `202` with a task id; the browser follows progress over SSE
(`/api/events`, `src/tasks/events.py`'s `broker`). Tests point the queue at
their temp-DB session factory — see `tests/conftest.py`. See
[ADR 08](../notes/decisions/08-task-runner.md) for the full design (an
in-process, non-persistent queue — deliberately simpler than the persisted
SQLite task-table design originally scoped for it).

**Secrets at rest** (provider/tracker OAuth tokens) are encrypted via
`src/core/crypto.py`, keyed by `LYCHEE_SECRET_KEY`. Unset ⇒ connecting an
account is refused rather than storing plaintext.

## Database

SQLite by default (`DATABASE_URL`, `sqlite:///./lychee.db` relative to
`backend/`), opened with `PRAGMA journal_mode=WAL`, `foreign_keys=ON`,
`busy_timeout=30000`. Schema changes go through Alembic — **never hand-edit the
schema or skip a migration**:

```sh
just db-revision "add foo table"   # autogenerate from model changes, review the diff
just db-migrate                    # upgrade to head
just db-check                      # error if models have drifted from the latest migration
just db-status                     # current revision / heads / history
```

On startup (`src/bootstrap.py`), the app auto-migrates to head and seeds default
rows (taxonomy, the default user, integration providers/trackers) — idempotent,
so this runs on every boot except in tests (`settings.auto_bootstrap = False`,
set in `tests/conftest.py`). Full-text search uses a **FTS5 `trigram`** virtual
table created by raw SQL (`src/catalog/search_index.py`), not part of
`Base.metadata` — it's created explicitly in both app bootstrap and test fixtures.

## Commands

Run from `backend/` (or via the root `justfile` — see `just --list`):

```sh
uv sync --extra dev              # install deps incl. dev extras
uv run uvicorn src.main:app --reload --reload-dir src --port 8000   # dev server
uv run ruff format . && uv run ruff check --fix .   # auto-fix lint + format
uv run basedpyright                                  # type-check
uv run pytest -q                                     # test
uv run ruff check . && uv run basedpyright && uv run pytest -q   # full CI gate, no auto-fix
```

**Always run the full gate (format → lint --fix → typecheck → test) before
considering backend work done.** `just be-check` runs the no-autofix version
(what CI runs); `just be-fix` auto-fixes first. A `PostToolUse` hook already
auto-runs ruff on every edited file, and a `Stop` hook blocks on outstanding
basedpyright errors — but pytest is not hooked, so run it explicitly.

## Testing

- One test file per API surface/module (`tests/test_<domain>_api.py`,
  `tests/test_<thing>.py`), pytest, `fastapi.testclient.TestClient`.
- `tests/conftest.py` provides `client` (a `TestClient` bound to a fresh temp
  SQLite DB + temp storage dir, schema created and seeded per test — see the
  `db_engine`/`db_session`/`client` fixtures) and `db_session` (for
  repository-level tests without going through HTTP). Every test gets a fully
  isolated database; there is no shared/global test DB.
- `tests/support.py` has factory helpers (e.g. `make_series`) for building
  fixtures inline in tests rather than via HTTP round-trips.
- The real MangaDex provider is replaced by an offline no-op
  (`_OfflineProvider` in `conftest.py`) so tests never hit the network.
- Background tasks run synchronously enough in tests that assertions can
  follow a `202` response immediately — check how existing tests in the same
  file await/poll task completion before assuming otherwise (patterns differ
  by domain; look at `tests/test_scan_api.py` or `tests/test_downloads_api.py`
  for scan/download-shaped flows).

## Config

Env vars (see `backend/.env.example`, loaded via `.env` + `pydantic-settings`):
`ENVIRONMENT`, `DATABASE_URL`, `STORAGE_PATH`, `LYCHEE_SECRET_KEY`,
`LYCHEE_ENCODE_WORKERS` (AVIF encode pool size — 1 = serial in-process),
`API_HOST`/`API_PORT`, `CORS_ORIGINS`, `LOG_LEVEL`/`LOG_FORMAT`. All settings
live in `src/core/config.py` (`Settings`); don't read `os.environ` directly
elsewhere.

## API contract

The backend is the source of truth for the API. After changing any
router/schema, regenerate the OpenAPI spec and the frontend's typed client
(from the repo root):

```sh
just api-gen
```

This runs `backend/scripts/dump_openapi.py` (writes `backend/openapi.json`)
then the frontend's `bun run api:gen`. Do this in the same change as the API
edit, not as a follow-up — the frontend build type-checks against the
generated client and will fail on drift.

## Architecture reference

Deeper design rationale (data model, scan pipeline, image serving, tagging,
metadata mapping, tracker sync, search tokenizer, etc.) lives in
[`../notes/decisions/`](../notes/decisions/) as numbered ADRs, each grounded
in the current implementation — read the relevant one before making a
structural change in that area.
