# lychee — task runner (https://github.com/casey/just)
# One entrypoint for the backend + frontend. Run `just` (or `just --list`) to see
# everything, grouped by surface.
#
# Ports:  backend 8000 · frontend dev 5173 · frontend preview 4173

set shell := ["bash", "-c"]

backend_dir := "backend"
frontend_dir := "frontend"

be_port := "8000"
fe_port := "5173"
fe_preview_port := "4173"

# Show all recipes (default).
default:
    @just --list

# ─────────────────────────────── backend ────────────────────────────────

# Install backend dependencies into backend/.venv (uv sync, incl. dev extras).
[group('backend')]
be-install:
    cd {{ backend_dir }} && uv sync --extra dev

# Reinstall backend dependencies from scratch — delete .venv, then resync.
[group('backend')]
be-reinstall: && be-install
    rm -rf {{ backend_dir }}/.venv

# Run the backend in dev mode (uvicorn --reload, auto-migrates + seeds) on :8000.
# Frees :8000 first so a stray backend can't silently block the bind.
[group('backend')]
be-dev: (kill-port be_port "backend")
    cd {{ backend_dir }} && uv run uvicorn src.main:app --reload --reload-dir src --host 0.0.0.0 --port {{ be_port }}

# Run the backend without reload (stable; use while editing tests/migrations) on :8000.
[group('backend')]
be-serve:
    cd {{ backend_dir }} && uv run uvicorn src.main:app --host 0.0.0.0 --port {{ be_port }}

# Seed a demo library into the dev database.
[group('backend')]
be-seed:
    cd {{ backend_dir }} && uv run python -m src.dev_seed

# Auto-fix backend lint + format (ruff format + ruff check --fix).
[group('backend')]
be-fix:
    cd {{ backend_dir }} && uv run ruff format . && uv run ruff check --fix .

# Lint + type-check + test the backend — the full CI gate (no auto-fix).
[group('backend')]
be-check:
    cd {{ backend_dir }} && uv run ruff check . && uv run basedpyright && uv run pytest -q

# Stop the backend.
[group('backend')]
be-stop: (kill-port be_port "backend")

# ─────────────────────────────── database ───────────────────────────────

# Run migrations — upgrade the database to the latest revision.
[group('database')]
db-migrate:
    cd {{ backend_dir }} && uv run alembic upgrade head

# Validate migrations — error if the models have drifted from the latest migration.
[group('database')]
db-check:
    cd {{ backend_dir }} && uv run alembic check

# Show migration status — current revision, heads, and recent history.
[group('database')]
db-status:
    cd {{ backend_dir }} && uv run alembic current && uv run alembic heads && uv run alembic history

# Autogenerate a new migration from model changes:  just db-revision "add foo table"
[group('database')]
db-revision message:
    cd {{ backend_dir }} && uv run alembic revision --autogenerate -m "{{ message }}"

# ─────────────────────────────── frontend ───────────────────────────────

# Install frontend dependencies (bun install).
[group('frontend')]
fe-install:
    cd {{ frontend_dir }} && bun install

# Reinstall frontend dependencies from scratch — delete node_modules, then re-install.
[group('frontend')]
fe-reinstall: && fe-install
    rm -rf {{ frontend_dir }}/node_modules

# Run the frontend dev server (proxies /api → :8000) on :5173.
[group('frontend')]
fe-dev:
    cd {{ frontend_dir }} && bun run dev --port {{ fe_port }}

# Run the frontend unit tests (vitest).
[group('frontend')]
fe-test:
    cd {{ frontend_dir }} && bun run test

# Type-check + test + build the frontend — the full CI gate.
[group('frontend')]
fe-check:
    cd {{ frontend_dir }} && bun run typecheck && bun run test && bun run build

# Build + serve the production bundle on :4173.
[group('frontend')]
fe-prod:
    cd {{ frontend_dir }} && bun run build && bun run preview --port {{ fe_preview_port }}

# Stop the frontend (dev + preview).
[group('frontend')]
fe-stop: (kill-port fe_port "frontend (dev)") (kill-port fe_preview_port "frontend (preview)")

# ─────────────────────────────── codegen ────────────────────────────────

# Regenerate backend/openapi.json, then the frontend's typed API client.
[group('codegen')]
api-gen:
    cd {{ backend_dir }} && uv run python scripts/dump_openapi.py
    cd {{ frontend_dir }} && bun run api:gen

# ──────────────────────────────── project ───────────────────────────────

# Install everything (backend + frontend).
[group('project')]
install: be-install fe-install

# Run the whole CI gate locally (backend + frontend).
[group('project')]
check: be-check fe-check

# Show which dev services are currently running.
[group('project')]
status:
    #!/usr/bin/env bash
    set -uo pipefail
    echo "lychee — dev process status"
    _row() {
      local pids; pids=$(lsof -ti tcp:"$1" 2>/dev/null || true)
      if [ -n "$pids" ]; then printf '  ● %-20s :%s  RUNNING (pid %s)\n' "$2" "$1" "$(echo $pids | tr "\n" " ")"
      else printf '  ○ %-20s :%s  stopped\n' "$2" "$1"; fi
    }
    _row {{ be_port }} backend
    _row {{ fe_port }} "frontend (dev)"
    _row {{ fe_preview_port }} "frontend (preview)"

# Stop EVERYTHING — backend + frontend — then sweep for stray dev processes.
[group('project')]
stop-all: be-stop fe-stop
    #!/usr/bin/env bash
    set -uo pipefail
    echo ""
    echo "Sweeping for stray dev processes…"
    for pat in "uvicorn src.main:app" "vite"; do
      pids=$(pgrep -f "$pat" 2>/dev/null || true)
      [ -n "$pids" ] && { echo "  ✓ killing '$pat' (pid $(echo $pids | tr "\n" " "))"; pkill -f "$pat" 2>/dev/null || true; }
    done
    echo "Done."

# ──────────────────────────────── helpers ───────────────────────────────

# (internal) Kill whatever is listening on a TCP port.
[private]
kill-port port name:
    #!/usr/bin/env bash
    set -uo pipefail
    pids=$(lsof -ti tcp:{{ port }} 2>/dev/null || true)
    if [ -n "$pids" ]; then
      echo "  ✓ stopping {{ name }} — port {{ port }} (pid $(echo $pids | tr "\n" " "))"
      kill $pids 2>/dev/null || true
    else
      echo "  · {{ name }} — nothing on port {{ port }}"
    fi
