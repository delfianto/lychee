# lychee

Self-hosted **manga / comic / ebook** media server.

Monorepo:

- **`backend/`** — Python 3.14 · FastAPI · SQLAlchemy 2.0 · Alembic · SQLite
- **`frontend/`** — Vue 3 · TypeScript · Vite · Tailwind CSS v4 · DaisyUI 5 (Bun)
- **`notes/`** — reference research + architecture decision records ([ADRs](notes/decisions/) 01–18)

## Quick start

Prereqs: [`uv`](https://docs.astral.sh/uv/), [`bun`](https://bun.sh/), [`just`](https://github.com/casey/just).

```sh
just be-install && just be-dev     # backend  → http://localhost:8000  (API docs: /docs)
just fe-install && just fe-dev     # frontend → http://localhost:5173
```

`just` (or `just --list`) shows every recipe (backend / database / frontend).

## Architecture

The full design lives in [`notes/decisions/`](notes/decisions/) as ADRs (monorepo, stack,
SQLite, domain model, scan pipeline, task queue, image serving, tagging, reading progress,
metadata providers, tracker sync, search, titles); the reference research that informed
them is in [`notes/`](notes/).

## Status

Early **bare skeleton** — the project structure and tooling are in place; features are
implemented against the ADRs.
