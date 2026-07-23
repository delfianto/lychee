# lychee — task runner (https://github.com/casey/just)
# One entrypoint for backend, database, and frontend. Run `just` to list recipes.
set shell := ["bash", "-c"]

backend_dir := "backend"
frontend_dir := "frontend"
be_port := "8000"
fe_port := "5173"

# Show all recipes.
default:
    @just --list

# ─────────────────────────── backend ───────────────────────────

# Install backend deps into backend/.venv (uv, incl. dev extras).
[group('backend')]
be-install:
    cd {{ backend_dir }} && uv sync --extra dev

# Run the backend (uvicorn --reload) on :8000.
[group('backend')]
be-dev:
    cd {{ backend_dir }} && uv run uvicorn src.main:app --reload --host 0.0.0.0 --port {{ be_port }}

# Lint + format (ruff).
[group('backend')]
be-lint:
    cd {{ backend_dir }} && uv run ruff format . && uv run ruff check --fix .

# Type-check (basedpyright, strict gate).
[group('backend')]
be-typecheck:
    cd {{ backend_dir }} && uv run basedpyright

# Run tests.
[group('backend')]
be-test:
    cd {{ backend_dir }} && uv run pytest

# Full backend QA gate: lint + typecheck + tests.
[group('backend')]
be-check: be-lint be-typecheck be-test

# ─────────────────────────── database ──────────────────────────

# Apply migrations to head.
[group('database')]
db-migrate:
    cd {{ backend_dir }} && uv run alembic upgrade head

# Autogenerate a migration:  just db-revision "add library table"
[group('database')]
db-revision message:
    cd {{ backend_dir }} && uv run alembic revision --autogenerate -m "{{ message }}"

# ─────────────────────────── frontend ──────────────────────────

# Install frontend deps (bun).
[group('frontend')]
fe-install:
    cd {{ frontend_dir }} && bun install

# Run the frontend dev server on :5173 (proxies /api to the backend).
[group('frontend')]
fe-dev:
    cd {{ frontend_dir }} && bun run dev

# Build the production bundle.
[group('frontend')]
fe-build:
    cd {{ frontend_dir }} && bun run build

# Type-check (vue-tsc).
[group('frontend')]
fe-typecheck:
    cd {{ frontend_dir }} && bun run typecheck

# Regenerate the typed API client from the backend's OpenAPI schema.
[group('frontend')]
fe-gen:
    cd {{ frontend_dir }} && bun run api:gen
