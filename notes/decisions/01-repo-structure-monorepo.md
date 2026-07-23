# 01 — Unified monorepo (backend + frontend)

**Status:** ✅ Accepted

## Context

lychee is a self-hosted app that ships as a **single deployable** (one server serving an API + a web UI). The reference research ([01-stack](../01-stack.md)) shows every project keeps a clean REST API regardless of frontend, and that the frontend is effectively "just another client". We are building both halves ourselves and want **minimal friction** and one source of truth for the API contract. The TBM project already proved a unified backend+frontend monorepo works well for exactly this shape.

## Decision

One git repository containing both halves at the root, mirroring TBM:

```
lychee/
├── backend/          # FastAPI app (own pyproject.toml, alembic, CLAUDE.md)
├── frontend/         # Vue SPA (own package.json, CLAUDE.md)
├── .claude/          # SHARED Claude config: merged permissions + path-scoped hooks
├── justfile          # task runner: one entrypoint for db / backend / frontend
├── openapi.json      # API contract, generated from backend, consumed by frontend
├── notes/            # this research + decisions
└── LICENSE / README.md
```

- **Shared `.claude/` at the repo root** with permissions and **path-scoped hooks** (a hook self-guards to its half: e.g. `ruff` only touches `backend/*.py`, the FE formatter only `frontend/*`). Claude Code must be **launched from the repo root** so `.claude/settings.json` loads (it is not hierarchical, unlike `CLAUDE.md`).
- **Root `justfile`** as the canonical entrypoint (`db-*`, `be-*`, `fe-*` recipes) — TBM pattern.
- **API contract in one place:** the backend generates `openapi.json`; the frontend generates a typed client from it (`bun run api:gen`). Any router/schema change → regenerate both.
- Each half keeps its **own `CLAUDE.md`/`AGENTS.md`** and toolchain (`uv` for backend, `bun` for frontend).

## Consequences

- One clone, one PR flow, one version, one CI — no cross-repo drift; the API contract can't get out of sync silently.
- Two toolchains (`uv` + `bun`) coexist in one repo — acceptable for a small/solo self-hosted project.
- Hooks must be path-scoped so backend hooks stay inert on frontend files and vice-versa.
- `.gitignore` will need frontend entries (`node_modules/`, `dist/`) added alongside the existing Python ones.

## Alternatives considered

- **Separate repos (backend + frontend).** Rejected: more friction, version drift, and the research shows the API contract must be kept in lockstep — trivial in a monorepo, painful across two.
- **Headless / backend-only (defer FE).** Rejected as the end state (we want the bundled reader UX), though the API-first design means we *could* ship headless first and add the SPA later without rework.
