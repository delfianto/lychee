# mcp/ — lychee agent-tool server

An MCP ([Model Context Protocol](https://modelcontextprotocol.io)) server that
lets an LLM agent drive lychee's batch/tedious library operations — bulk
tagging, bulk downloads, finding unmatched/untagged series — instead of
clicking through the webapp one series at a time. See the [repo-root
AGENTS.md](../AGENTS.md) for the monorepo overview and
[`../notes/plan.md`](../notes/plan.md) PART J for the architecture decision
behind this directory existing at all; this file covers `mcp/` specifically.

## What this is (and isn't)

**This server is a client of the backend's REST API** — the same relationship
`frontend/` has to `backend/` — not a new consumer of the ORM/service layer.
Every tool here is either a thin wrapper over an existing endpoint or
orchestration (paginate-then-filter, fetch-then-patch) over a handful of
existing endpoints. **No backend changes were needed to build this** — every
field these tools write (`tagIds`, `favorite`, `libraryStatus`, downloads)
already exists on the current API contract.

It is **not** part of "the one deployable" (backend + frontend, per the root
`CLAUDE.md`). It's optional tooling you run only if you want agent access to
the library — nothing else in the repo depends on it.

## Stack

- **Runtime:** Python 3.14, managed by [`uv`](https://docs.astral.sh/uv/) (`mcp/.venv`) — mirrors `backend/`.
- **Framework:** [FastMCP](https://gofastmcp.com) — `@mcp.tool` decorator, `fastmcp run`/`dev`/`call` CLI.
- **HTTP client:** `httpx.AsyncClient` against the backend's REST API. No
  OpenAPI-codegen client (yet) — the handful of endpoints in use are
  hand-typed in `src/models.py`; revisit if the tool surface grows
  significantly (see plan.md PART J, "Open before starting").
- **Config:** `pydantic-settings` (`src/settings.py`) — one setting,
  `LYCHEE_API_URL`.
- **Quality gate:** ruff (lint + format), basedpyright (`standard` mode), pytest — identical shape to `backend/`.

Not present, on purpose: **no auth**. This server runs on stdio transport
(spawned as a subprocess by whatever MCP client uses it — Claude Desktop,
Claude Code, etc.), which has no network listener at all — there is nothing
to authenticate against yet. See "Transport + auth" in plan.md PART J before
ever adding an HTTP/SSE transport; that is the point auth actually starts to
matter, not before.

## Layout

```
server.py        # entrypoint — `mcp.run()`. Deliberately outside src/, see below.
src/
  app.py           # the bare FastMCP instance (`mcp`) — no other project imports
  client.py         # LycheeClient — the httpx wrapper over the backend's REST API
  models.py           # Hand-typed CamelModel mirrors of the backend response shapes in use
  settings.py           # LYCHEE_API_URL (pydantic-settings, .env support)
  tools/
    series.py               # list_series, get_series, find_untagged_series,
                              # find_unmatched_series, bulk_tag_series,
                              # bulk_set_favorite, bulk_set_library_status
    downloads.py              # bulk_queue_downloads, list_downloads
    libraries.py                # list_libraries, scan_library
    taxonomy.py                   # list_taxonomy
tests/
  test_client.py    # LycheeClient tests via httpx.MockTransport (offline, no live backend)
```

**`server.py` lives at the top level, not `src/server.py` — don't move it.**
`fastmcp run`/`call`/`dev` load whatever file they're pointed at as a raw
script with no package context, so that file can't use relative imports.
Keeping it outside `src/` means Python puts `mcp/` (not `mcp/src/`) on
`sys.path`, so `server.py`'s plain `from src.app import mcp` / `import
src.tools` resolve `src` as a normal top-level package. Everything *inside*
`src/` (including `tools/*.py`, which do `from ..app import mcp`) keeps
ordinary relative imports — they're only ever reached via a real `import`,
never executed directly, so they never hit this problem. `app.py` holds
nothing but the bare `FastMCP(...)` instance for exactly this reason: no
project imports there means no risk of it being pulled in twice under two
different names.

## Conventions

- **Tools return plain dicts/lists, not Pydantic model instances** —
  `model.model_dump(by_alias=True)` at the tool boundary, so the JSON an
  agent sees matches the backend's own camelCase wire format exactly (same
  field names as the webapp's network tab).
- **Batch tools never abort partway through.** Each `bulk_*` tool loops over
  its ids, catches per-item failures into a `failed: {id: reason}` map, and
  keeps going — the return shape is always `{updated: [...], failed: {...}}`
  (or `queued`/`failed` for downloads). One bad id in a batch of 50 shouldn't
  cost you the other 49.
- **`bulk_tag_series` fetches before it patches** for `add`/`remove` modes
  (needs the series' current tag list to union/subtract against) — `replace`
  mode skips that read. Keep this in mind if you add more bulk-edit tools
  that need read-modify-write semantics.
- Error messages surface the backend's own `{"error": {"message"}}` body
  (`client._error_message`) rather than a bare HTTP status, so a failure is
  something an agent can actually reason about.

## Commands

Run from `mcp/` (or via the root `justfile` — see `just --list`):

```sh
uv sync --extra dev                          # install deps incl. dev extras
uv run fastmcp dev inspector server.py       # interactive testing (browser UI)
uv run fastmcp call server.py list_series limit=5       # call one tool from the CLI
uv run ruff format . && uv run ruff check --fix .       # auto-fix lint + format
uv run basedpyright                                      # type-check
uv run pytest -q                                          # test
uv run ruff check . && uv run basedpyright && uv run pytest -q   # full CI gate, no auto-fix
```

The backend must be running (`just be-dev`) for anything beyond `pytest` —
every tool call is a real HTTP request to `LYCHEE_API_URL`.

**Always run the full gate before considering a change done** — `just
mcp-check` runs it from the repo root; `just mcp-fix` auto-fixes first.

## Testing

- `tests/test_client.py` exercises `LycheeClient` against `httpx.MockTransport`
  with canned JSON responses — no live backend, no network. This mirrors the
  pattern `backend/`'s own MangaDex client tests use.
- The `tools/*.py` functions themselves are exercised end-to-end against a
  real running backend (`just be-dev` + `just mcp-call ...` or the Inspector),
  not unit-tested in isolation — they're thin enough that the client-layer
  tests plus a live smoke pass cover the real risk (HTTP mapping / error
  shapes), and a live backend is the only thing that can validate the actual
  request/response contract stays in sync.

## Config

`LYCHEE_API_URL` (see `.env.example`) — base URL of the backend's REST API,
default `http://127.0.0.1:8000`. Nothing else yet; don't add a setting before
something actually reads it (see plan.md PART J on why auth isn't here yet).

## Architecture reference

The decision to make this a separate directory (rather than
`backend/src/mcp/`), the stdio-first transport choice, and exactly when an
API-key auth layer would earn its keep are all recorded in
[`../notes/plan.md`](../notes/plan.md) **PART J** — read that before
restructuring anything here or adding a transport/auth layer.
