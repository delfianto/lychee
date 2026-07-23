# 12 — Authentication & users (deferred; single-user v1)

**Status:** ✅ Accepted (scope decision)

## Context

Multi-user and authentication are **not** a priority — core functionality comes first. The references validate this: LANraragi ships **one shared password**, KamiYomu an **optional single-admin basic auth** (plaintext), Mango a simple username/session; **only Komga** does real multi-user + roles + per-library access. "No fancy auth" is the norm in this space, so deferring it is low-risk. This touches [10](10-tagging-content-rating.md) (per-user content filter) and [11](11-reading-progress.md) (per-user progress), which assumed multi-user.

## Decision

- **No authentication and no multi-user in v1.** No login, sessions, roles/RBAC, API keys, or per-library access control. The app runs open; remote exposure is the operator's job (bind to localhost, reverse proxy, or VPN) — the self-hosted norm.
- **Keep the data model user-aware, resolving to a single seeded `default` user.** `reading_progress`, `series_read_progress`, and future per-user settings (the content-rating filter) keep their `user_id`, always pointing at that one default user. Since the project is greenfield this costs ~nothing and preserves the option to add auth later **without migrating those tables** — avoiding the "single-user baked in is painful to retrofit" trap flagged in [11](11-reading-progress.md).
- Per-user constructs from 10/11 therefore still work end-to-end; they just resolve to the default user for now.

## Backlog (when revisited)

A minimal auth story matching this space, added in order of value:
1. **Single shared password + API key** (LANraragi's bar) — cheapest, covers "put it on the internet safely".
2. Only if ever wanted: **Komga-style multi-user** — users, roles (`ADMIN` / download / stream / sync), per-library access, and per-user content restrictions (the 10 content-rating cap becomes real).

Nothing in v1 should preclude this; the user-aware schema is the single forward-looking hook. If/when we add a "production" bind-to-all mode, mirror TBM's "refuse to boot with insecure defaults" validator.

## Consequences

- Simpler v1: no auth middleware, no user-management UI, no session/token handling.
- 10/11 stay valid as written (resolve to the default user) — no rework, no contradiction.
- Remote-exposure safety is documented as an operator responsibility for now.
- Adding auth later = add login + more user rows + gate endpoints; **no schema migration** of progress/settings tables.

## Alternatives considered

- **Full multi-user + roles now** (Komga) — rejected: not a priority; most self-hosted installs are single-user; premature.
- **Drop `user_id` entirely (pure single-user schema)** — viable while greenfield, but rejected as the default: keeping the column costs ~nothing and avoids a later retrofit. Trivial to flip on paper if preferred.
- **Basic-auth single admin now** (KamiYomu) — deferred to the backlog; unneeded for local-first core development.
