# 12 — Authentication & users (deferred; single-user v1)

**Status:** Implemented as scoped (no auth) — but see "What actually got
built" below: the "keep the schema user-aware" half of the original
decision did not happen.

## What this is

**No authentication and no multi-user.** No login, sessions, roles/RBAC, API
keys, or per-library access control anywhere in the backend. The app runs
open; remote exposure (bind to localhost, reverse proxy, VPN) is the
operator's job. `backend/CLAUDE.md` states this plainly: "no auth/session
layer (single implicit 'default' user)."

## What actually got built

The original plan was to keep the schema **user-aware** — a seeded default
`User` row, `user_id` columns on `reading_progress` and per-user settings —
so multi-user could be added later without migrating those tables. That
part **did not ship**:

- No `User` model/table exists anywhere.
- No `user_id` column on `ReadingProgress` ([11](11-reading-progress.md) —
  it's keyed by `chapter_id` alone).
- No seeded "default user" row — `seed.py`'s `seed_all()` seeds only
  taxonomy and integrations.
- "Per-user" state (`favorite`, `library_status`, `user_rating`) lives as
  plain columns directly on `Series` — the rejected alternative ("drop
  `user_id` entirely, pure single-user schema") is what actually got built.

**Consequence:** turning on multi-user later now *will* require a real
schema migration (adding `user_id` where it's missing, moving per-user
fields off `Series`) — the retrofit-avoidance this ADR was originally
written to buy didn't materialize. Worth knowing before assuming multi-user
is a config flip away.

## Backlog (when revisited)

Unchanged from the original plan, still the intended order:
1. **Single shared password + API key** — cheapest, covers "put it on the
   internet safely." (`mcp/`'s own auth story — see
   [`mcp/AGENTS.md`](../../mcp/AGENTS.md) "Transport + auth" — treats this
   as backlog item #1 too, to land on its own listener first if it ever
   goes network-reachable, before promoting the same mechanism to the main
   API.)
2. Only if ever wanted: full multi-user (users, roles, per-library access,
   per-user content-rating caps).

Nothing in v1 depends on either happening.
