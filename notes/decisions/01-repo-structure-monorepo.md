# 01 — Unified monorepo (backend + frontend + mcp)

**Status:** Implemented.

## What this is

One repository holding three components: `backend/` (own `pyproject.toml`,
Alembic migrations, `.venv`), `frontend/` (own `package.json`, Vite/Bun
toolchain), and `mcp/` (own `pyproject.toml`, `.venv`) — plus `notes/` (this
directory) and a root `justfile` as the single entrypoint for all three.

`mcp/` is a **client of the backend's REST API**, the same way `frontend/` is
— not a new consumer of the ORM/service layer, and no backend changes were
needed to build it (`mcp/AGENTS.md`).

```
lychee/
├── backend/    Python 3.14 · FastAPI · SQLAlchemy 2.0 · Alembic · SQLite
├── frontend/   Vue 3 · TypeScript · Vite · Tailwind v4 · DaisyUI 5 · Bun
├── mcp/        MCP server — REST client of the backend, agent-tool access to the library
├── notes/      architecture decisions (this directory) + plan.md + refactor.md
└── justfile    canonical task runner — one entrypoint for db / backend / frontend / mcp
```

Root `AGENTS.md` (`CLAUDE.md` is a symlink to it, same pattern repeated in
each subdirectory) covers monorepo-wide concerns; each half has its own
`AGENTS.md` for stack/convention details specific to it. `backend/openapi.json`
lives inside `backend/`, not at the repo root.

## The API contract link

The one thing that spans backend and frontend: the backend generates
`backend/openapi.json` (`backend/scripts/dump_openapi.py`); the frontend
generates a typed client from it (`frontend/src/api/schema.d.ts`, via
`openapi-typescript`). `just api-gen` regenerates both in one step — any
router/schema change needs to ship this in the same change, or the frontend
type-checks against a stale contract.

## Tooling

- `.claude/settings.json` hooks are **path-scoped**: `PostToolUse` runs
  `be-linter.sh` only on `*/backend/*.py` and `fe-linter.sh` only on
  `*/frontend/*`; `Stop` blocks on `be-typecheck.sh`/`fe-typecheck.sh`
  similarly split. `mcp/` has no hook — its quality gate is manual
  (`mcp/AGENTS.md`).
- Each half keeps its own `.gitignore` (`backend/.gitignore`,
  `frontend/.gitignore`) plus a slim root one for cross-cutting/OS cruft,
  rather than one shared file.
- `justfile` recipe groups: `be-*`, `fe-*`, `db-*`, `mcp-*`, plus
  `install`/`check`/`status`/`stop-all`/`api-gen` that span all three.

## Why one repo

Changes that cross the API boundary (new endpoint, changed response field)
touch backend and frontend atomically in one commit/PR instead of coordinating
two repos and a version pin between them. A solo/small-team self-hosted
project doesn't need the isolation two repos would buy, and shared root
tooling (hooks, `justfile`, this ADR set) only has to exist once.
