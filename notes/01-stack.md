# Overview 1 — Stack

Cross-project comparison of language, framework, datastore, jobs, API, and auth.
Per-project detail: [komga](komga/README.md) · [kamiyomu](kamiyomu/README.md) · [mango](mango/README.md) · [lanraragi](lanraragi/README.md).

## Comparison

| Aspect | Komga | KamiYomu | Mango | LANraragi |
|---|---|---|---|---|
| Language / runtime | Kotlin 2.2 (JVM 21) | C# / .NET 8 | Crystal 1.0 (native) | Perl 5.36 |
| Web framework | Spring Boot 3.5 (WebMVC) | ASP.NET Core 8 (Razor + MVC) | Kemal 1.0 | Mojolicious 9.39 |
| Frontend | Vue 2.6 + Vuetify 2 SPA (`komga-webui`) | Razor Pages + HTMX + SignalR (no SPA) | ECR server-render + Gulp JS | TT2 + jQuery/DataTables→Preact |
| Primary datastore | SQLite (`sqlite-jdbc`) | LiteDB (BSON documents) | SQLite (`crystal-sqlite3`) | Redis (5 logical DBs) |
| DB access | jOOQ 3.19 (codegen DSL) | LiteDB LINQ | raw hand-written SQL | Redis commands + Lua |
| Migrations | Flyway 11 (SQL + Kotlin) | **none** | `mg` numbered `.cr` | **none** |
| Secondary stores | Lucene 9.9 index dir; `tasks.sqlite` | 5 LiteDB files + Hangfire SQLite | gzipped-YAML library cache; LRU | Redis DB1 (Minion), DB3 (search) |
| Background jobs | SQLite task queue + `ThreadPoolTaskExecutor` | Hangfire 1.8 (SQLite storage) | Crystal fibers (`spawn` + `sleep`) | Minion 10 (Redis backend) |
| Scheduling | per-library `ScanInterval` (Spring) | Hangfire recurring (daily discovery) | fiber loop every N min | Shinobu watcher + Minion |
| API styles | REST v1, OPDS 1.2 + 2.0, WebPub, KOReader, Kobo, SSE | REST (versioned) + OPDS 1.2 + SignalR | ad-hoc JSON REST + OPDS v1 | REST + OpenAPI 3 + OPDS Atom |
| API docs | springdoc-openapi | Swashbuckle/Swagger | `koa` → `/openapi.json` | OpenAPI yaml + Redocly |
| Auth | session, HTTP Basic, API key, OAuth2/OIDC; **roles + multi-user** | optional HTTP Basic (single admin, plaintext) | session cookie, HTTP Basic, proxy header; **users** | single shared bcrypt password + API key |
| Packaging | Gradle; Docker; Conveyor desktop | `dotnet`; Docker (Chromium bundled) | single static binary; Alpine Docker | Docker (`ghcr`), Redis bundled |
| Dev run | `./gradlew bootRun` | `dotnet run` | `make run` (interpreted) | `script/lanraragi daemon` |

## Observations

- **SQLite is the consensus embedded store** for scan-index servers (Komga, Mango). The two that went another way both pay for it: KamiYomu's **LiteDB has no migration story** ("schema evolves from collection names only"), and LANraragi's **Redis-as-database** gives up referential integrity and forces `KEYS`/Lua for anything relational.
- **Everyone offloads heavy work** (scan, thumbnails, import) to an async mechanism. The persisted-queue approaches (Komga's `tasks.sqlite`, KamiYomu's Hangfire, LANraragi's Minion) survive restarts; Mango's in-process fibers do not.
- **Komga's task queue has two features worth copying**: a **priority** column and a **group-id** that serializes tasks for the same series while allowing cross-series parallelism.
- **Two-process split** (LANraragi: Shinobu watcher + Minion workers, separate from the web process) cleanly separates "notice a change" from "do the slow work".
- **Auth maturity tracks multi-user maturity.** Komga (roles: `ADMIN`, `FILE_DOWNLOAD`, `PAGE_STREAMING`, `KOBO_SYNC`, `KOREADER_SYNC`; per-user content restrictions) is the model; the single-user projects (KamiYomu plaintext Basic, LANraragi one shared password) show how hard users are to retrofit.
- **Frontend spread** is wide: full Vue SPA (Komga) → HTMX partials (KamiYomu) → server-rendered templates (Mango, LANraragi). For a Python backend, any of these work; HTMX/server-render minimizes JS toolchain burden, an SPA maximizes UX flexibility.

## Recommendation for lychee

- **Runtime/framework:** Python 3.14 + FastAPI (async, OpenAPI built-in, SSE via `sse-starlette`). Matches the existing house stack.
- **Datastore:** **SQLAlchemy 2.0 + SQLite + Alembic**. This is the validated default and gives the migrations LiteDB/Redis lack. Enable WAL mode. Keep an eye on write-serialization (SQLite single-writer) for the scan/progress paths.
- **Search:** **SQLite FTS5** to start (it's in the engine, zero ops). Budget for a swap to **Tantivy/Meilisearch** if CJK n-gram search becomes a requirement — this is exactly the wall Komga hit and why it runs Lucene.
- **Background jobs:** a persisted queue. Options: **ARQ** (async, Redis) or **Celery** (mature, broker required) or a **SQLite-backed queue + APScheduler** to stay dependency-light like Komga. Copy Komga's **priority + per-series group serialization**. Split "watcher" and "worker" concerns even if they start in one process.
- **API:** REST + **OPDS 1.2** (2.0 optional). Auto-generate the OpenAPI schema (FastAPI does this natively).
- **Auth & multi-user:** design **users + roles + per-user library access/content restrictions from day one** (Komga). Session or JWT; API keys for OPDS/reader clients. Do **not** ship single-user and bolt users on later.
- **Packaging:** Docker-first with env-var config overrides (all four do this); relative paths resolve under a config dir (`~/.lychee` style), absolute in containers.
