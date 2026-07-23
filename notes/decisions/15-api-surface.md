# 15 — API surface & client scope

**Status:** ✅ Accepted (scope decision)

## Context

The **only** client is the lychee webapp (the Vue SPA, [03](03-frontend-stack.md)). This narrows the API and **reverses** the "external sync ecosystem" assumptions in [11](11-reading-progress.md) (Tachiyomi/Mihon, KOReader, Kobo, OPDS Position Sync) and the **Komga-API-compatibility** option floated there.

## Decision

- **Internal REST API, for the webapp only.** FastAPI + JSON, with an **OpenAPI-generated typed client** for the SPA ([03](03-frontend-stack.md)). Shaped purely for our UI's needs — **no obligation to match any external schema**, free to evolve with the frontend.
- **SSE** for live updates (scan/progress/thumbnail events) to the webapp ([07](07-scan-pipeline.md)/[08](08-task-runner.md)).
- **Auth:** none in v1 — the API is open/local ([12](12-auth-users.md)).
- **Explicitly out of scope (backlog):** OPDS (1.2/2.0), third-party reader-client compatibility, **Komga-API compatibility**, KOReader / Kobo **device sync**, Tachiyomi/Mihon. These are documented as options in [../04-reading-tracker.md] but not chosen — there is no non-webapp client to serve them.
- **Retained external integration:** outbound **read-status tracker sync** → [16](16-tracker-sync.md).

## Consequences

- Smaller surface, faster to build, and the API can change freely alongside the UI (no external contract to preserve).
- No device/OPDS ecosystem work; the "sync" investment goes entirely into trackers ([16](16-tracker-sync.md)).
- Reversible: the clean REST API + the entity model don't preclude adding OPDS or a public API later if a non-webapp client ever appears.

## Alternatives considered

- **Expose OPDS / aim for client-compat now** (all four reference servers expose OPDS) — rejected: unused surface given a webapp-only client. Revisit only if that changes.
