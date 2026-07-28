# Architecture Decisions

ADRs (Architecture Decision Records) for **lychee**, describing the system
**as actually implemented** — each is grounded in real file paths, models,
and functions, not just the reasoning that led there. Where a decision's
first draft and what shipped diverged, the ADR says so directly rather than
leaving the stale version to be discovered by reading code separately.
Comparative research on adjacent projects (Komga, LANraragi, Mango,
KamiYomu, the MangaDex API) that originally informed some of these lives in
the sibling directories one level up (`../komga/`, `../lanraragi/`,
`../mango/`, `../kamiyomu/`, `../mangadex-api/`).

| # | Decision | Status |
|---|---|---|
| [01](01-repo-structure-monorepo.md) | Unified monorepo (backend + frontend + mcp) | Implemented |
| [02](02-backend-stack.md) | Backend: Python 3.14 + FastAPI + SQLAlchemy + Alembic | Implemented |
| [03](03-frontend-stack.md) | Frontend: Vue 3 + Tailwind + DaisyUI (SPA) | Implemented |
| [04](04-database-sqlite.md) | Database: SQLite (WAL) + FTS5 trigram for search | Implemented — FTS5 table never created outside tests, see the ADR |
| [05](05-domain-model.md) | Domain data model & filesystem mapping (Library → Series → Book → Chapter) | Implemented |
| [06](06-filename-parser.md) | Filename / volume-chapter parser | Implemented |
| [07](07-scan-pipeline.md) | Library scan pipeline | Implemented — manual/on-demand only, no watcher or scheduler |
| [08](08-task-runner.md) | Task runner: in-process thread-pool queue | Implemented — much simpler than originally scoped, see the ADR |
| [09](09-image-serving.md) | Image, thumbnail & page-serving pipeline | Implemented for CBZ/ZIP/image directories |
| [10](10-tagging-content-rating.md) | Tagging, content rating & taxonomy | Implemented |
| [11](11-reading-progress.md) | Reading progress & sync | Implemented — single-user, chapter-keyed |
| [12](12-auth-users.md) | Auth & users — deferred, single-user v1 | Implemented as scoped (no auth) |
| [13](13-metadata-providers.md) | Metadata providers & optional downloader | Implemented — MangaDex only |
| [14](14-metadata-mapping.md) | Metadata field mapping & lock-merge rules | Implemented — no embedded-format (ComicInfo/OPF) support |
| [15](15-api-surface.md) | API surface & client scope — internal webapp-only | Implemented |
| [16](16-tracker-sync.md) | Read-status tracker sync | Implemented — AniList/MyAnimeList/MangaUpdates + MangaDex two-way; no Kitsu |
| [17](17-search-fts.md) | Full-text search tokenizer — FTS5 `trigram` | Implemented in code — see ADR 04's production gap |
| [18](18-title-variants.md) | Title & name variants | Implemented — storage only, no display-resolution logic |
| [19](19-avif-storage.md) | AVIF as the served image format | Implemented |
| [20](20-lychee-info-metadata.md) | `lychee.info` — native YAML metadata sidecar | Implemented — reader and writer both |
| [21](21-tag-aliases.md) | Tag aliases — synonym resolution + a renamable display label | Implemented |

## Open questions

None outstanding. (The three originally tracked here — page storage, task
runner design, FTS tokenizer choice — are all resolved; see the linked ADRs
above rather than a separate log of the resolution.)
