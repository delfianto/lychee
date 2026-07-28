# lychee

Self-hosted **manga / comic / ebook** media server (scan-and-index): point it at a
library on disk, it indexes series/chapters, serves pages as generated images, and
tracks reading progress. Single deployable — one backend process serves both the
API and (in production) the built frontend.

## Monorepo layout

```
lychee/
├── backend/    Python 3.14 · FastAPI · SQLAlchemy 2.0 · Alembic · SQLite — see backend/AGENTS.md
├── frontend/   Vue 3 · TypeScript · Vite · Tailwind v4 · DaisyUI 5 · Bun — see frontend/AGENTS.md
├── mcp/        MCP server (agent-tool access to the library) — a client of the backend's
│               REST API, not part of the one deployable — see mcp/AGENTS.md, notes/plan.md PART J
├── notes/      architecture decisions (ADRs, notes/decisions/01–21) grounded in the
│               current implementation; also plan.md (build-status tracker) + refactor.md
│               (code-quality backlog) + comparative research on adjacent projects
└── justfile    canonical task runner — one entrypoint for db / backend / frontend / mcp
```

**This file covers monorepo-wide concerns only.** For anything specific to one
surface — stack details, module layout, conventions, test patterns, commands —
read **[backend/AGENTS.md](backend/AGENTS.md)**, **[frontend/AGENTS.md](frontend/AGENTS.md)**,
or **[mcp/AGENTS.md](mcp/AGENTS.md)**, whichever the task touches. Most real
work happens in one at a time; read backend + frontend both when a change
crosses the API boundary (new/changed endpoint, new response field, etc.).

## The one thing that spans both halves: the API contract

The backend generates `backend/openapi.json`; the frontend generates a typed
client from it (`frontend/src/api/schema.d.ts`). Any router or schema change in
`backend/` requires regenerating both, in the **same** change:

```sh
just api-gen
```

Skipping this leaves the frontend type-checking against a stale contract —
`bun run build` will fail (or worse, silently pass against outdated types if
the drift doesn't happen to trip the compiler).

## Running things — use the justfile

The root `justfile` is the canonical entrypoint for both halves and the
database; run `just --list` for the full, grouped recipe list. Highlights:

```sh
just install          # be-install + fe-install + mcp-install
just be-dev           # backend dev server, :8000, auto-reload (frees the port first)
just fe-dev           # frontend dev server, :5173 (proxies /api → :8000)
just mcp-dev          # MCP server in the browser-based Inspector (needs be-dev running)
just check            # full CI gate, everything (be-check + fe-check + mcp-check)
just db-migrate       # upgrade the database to head
just api-gen          # regenerate openapi.json + the frontend client
just status           # what's currently listening on the dev ports
just stop-all         # stop everything + sweep stray dev processes
```

Prefer `just <recipe>` over reconstructing the underlying `uv`/`bun`/`alembic`
command by hand — the recipes encode things worth not forgetting (e.g. `be-dev`
frees `:8000` first; `db-check` catches model/migration drift).

## Architecture decisions

Design rationale — why SQLite over Postgres, the domain model and filesystem
mapping, the scan pipeline, the task runner, image serving, tagging, metadata
provider/mapping rules, tracker sync, the search tokenizer, title variants —
is recorded as numbered ADRs in **[`notes/decisions/`](notes/decisions/)**
(start at its `README.md` for the index). Each ADR describes the system **as
actually implemented** — grounded in real file paths and functions, not just
the reasoning that led there — including calling out where an early design
didn't survive contact with the codebase. Comparative research on adjacent
projects (Komga, LANraragi, Mango, KamiYomu, the MangaDex API) that informed
some of these decisions lives in sibling directories under `notes/`
(`notes/komga/`, `notes/lanraragi/`, etc.), not in the ADRs themselves. Read
the relevant ADR before making a structural change in that area.

For **current status** — what's implemented, what's partial, what's
deliberately not planned — check `notes/plan.md` before assuming a feature is
missing or planning it as new work. For known code-quality issues and
in-progress cleanup, see `notes/refactor.md`.

## Conventions that apply everywhere

- **Work on the current branch.** Don't create branches or push unless
  explicitly asked.
- Each surface keeps its own toolchain and quality gate — see
  `backend/AGENTS.md` / `frontend/AGENTS.md` / `mcp/AGENTS.md` for the exact
  commands — but the shape is the same everywhere: format/lint, type-check,
  test, in that order, before calling a change done.
- Don't add a dependency, abstraction, or config knob "for later." Both ADRs
  and `notes/plan.md` are explicit about what's in scope; unplanned scope creep
  (e.g. OPDS support, multi-user auth) has usually already been considered
  and deliberately deferred — check `notes/decisions/` before reintroducing it.
