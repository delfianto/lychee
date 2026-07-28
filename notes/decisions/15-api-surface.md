# 15 — API surface & client scope

**Status:** Implemented.

## What this is

An internal REST API for the webapp (and, since [01](01-repo-structure-monorepo.md),
`mcp/`) — not a public/OPDS-compatible surface. FastAPI + JSON, mounted
unversioned at `/api` (no `/v1` segment). SSE (`/api/events`) for live
scan/download/task updates. No auth ([12](12-auth-users.md)) — the API is
open/local, remote exposure is the operator's job.

Routers registered in `backend/src/main.py`: `health`, `catalog`, `library`,
`progress`, `integrations`, `taxonomy`, `collections`, `tasks`, `downloads`,
`fs` — nine domains, all webapp-internal. No OPDS route exists (`grep` for
`opds` across the codebase returns nothing).

## Why not OPDS / device-sync

**Explicitly out of scope:** OPDS (1.2/2.0), third-party reader-client
compatibility (Tachiyomi/Mihon, KOReader, Kobo device sync), Komga-API
compatibility. The API is shaped purely for lychee's own UI's needs, free to
evolve with the frontend with no external schema to preserve — there's no
non-webapp client to serve. The one retained external integration is
**outbound** read-status tracker sync ([16](16-tracker-sync.md)), which
needs no special client-facing protocol, just the sync client's own OAuth
flow.

This is a scope decision, not a technical limitation — the REST API + typed
OpenAPI contract don't preclude adding a public API or OPDS later if a
non-webapp client ever actually shows up; `mcp/` is proof the "second REST
client" path already works without reopening this decision.
