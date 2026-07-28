# Architecture Decisions

Lightweight ADRs (Architecture Decision Records) for **lychee** — "what we shall do".
Each records a decision, why, the consequences, and the alternatives we rejected.
Grounded in the reference research one level up ([`../00-overview.md`](../00-overview.md)).

| # | Decision | Status |
|---|---|---|
| [01](01-repo-structure-monorepo.md) | Unified monorepo (backend + frontend in one repo, TBM-style) | ✅ Accepted |
| [02](02-backend-stack.md) | Backend: Python 3.14 + FastAPI + SQLAlchemy + Alembic | ✅ Accepted |
| [03](03-frontend-stack.md) | Frontend: Vue 3 + Tailwind + DaisyUI (SPA) | ✅ Accepted |
| [04](04-database-sqlite.md) | Database: SQLite (WAL) + FTS5 trigram for search | ✅ Accepted |
| [05](05-domain-model.md) | Domain data model & filesystem mapping (hybrid; loose-image books) | ✅ Accepted |
| [06](06-filename-parser.md) | Filename / volume-chapter parser (adopt-and-extend; specials as decimals) | ✅ Accepted |
| [07](07-scan-pipeline.md) | Library scan pipeline (watcher + periodic; resolve → analyze → order → reconcile) | ✅ Accepted |
| [08](08-task-runner.md) | Task runner: custom SQLite-backed queue + APScheduler | ✅ Accepted |
| [09](09-image-serving.md) | Image, thumbnail & page-serving pipeline | ✅ Accepted |
| [10](10-tagging-content-rating.md) | Tagging, content rating & taxonomy (MangaDex-modeled) | ✅ Accepted |
| [11](11-reading-progress.md) | Reading progress & sync (per-user; phased ecosystem sync) | ✅ Accepted |
| [12](12-auth-users.md) | Auth & users — deferred; single-user v1 (schema stays user-aware) | ✅ Accepted |
| [13](13-metadata-providers.md) | Metadata providers & (optional) downloader (MangaDex first) | ✅ Accepted |
| [14](14-metadata-mapping.md) | Metadata field mapping & lock-merge rules | ✅ Accepted |
| [15](15-api-surface.md) | API surface & client scope — internal webapp-only (OPDS/device-sync out) | ✅ Accepted |
| [16](16-tracker-sync.md) | Read-status tracker sync (AniList/MAL/Kitsu/MangaUpdates/MangaDex) | ✅ Accepted |
| [17](17-search-fts.md) | Full-text search tokenizer — FTS5 `trigram` (CJK + substring) | ✅ Accepted |
| [18](18-title-variants.md) | Title & name variants — language-tagged titles (native/romanized/English) | ✅ Accepted |
| [19](19-avif-storage.md) | AVIF as the served image format (`Cover.avif`, content-aware presets) | ✅ Accepted |
| [20](20-lychee-info-metadata.md) | `lychee.info` — native YAML metadata sidecar (LLM-authored) | ✅ Accepted |
| [21](21-tag-aliases.md) | Tag aliases — synonym resolution + a renamable display label | ✅ Accepted |

**Status legend:** ✅ Accepted · 🟡 Proposed · ⚪ Superseded

## Open questions (tracked, not yet decided)

- ~~**Page storage**~~ — **Resolved: no page table.** Store `page_count` on the book + current page on the progress row; derive the page↔entry mapping on demand (cached). See [04](04-database-sqlite.md#open-page-storage).
- ~~**Task runner**~~ — **Resolved: custom SQLite-backed queue + APScheduler** (broker-less; priority + per-series serialization). See [08](08-task-runner.md).
- ~~**FTS tokenizer default**~~ — **Resolved: FTS5 `trigram` everywhere** (single index; CJK + substring; hybrid/Tantivy as escape hatches). See [17](17-search-fts.md).

_All initial open questions are now resolved._
