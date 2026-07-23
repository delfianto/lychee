# 02 — Backend: Python 3.14 + FastAPI + SQLAlchemy + Alembic

**Status:** ✅ Accepted

## Context

lychee is a **scan-and-index media server** (see the three archetypes in [00-overview](../00-overview.md)). The research consensus favors a layered server with an async job mechanism, embedded metadata parsing, and archive/image handling — all well-served by Python. We also want to reuse TBM's house stack and conventions (and its `.claude` hooks — see [01](01-repo-structure-monorepo.md)).

## Decision

Same core stack as TBM:

- **Runtime:** Python 3.14 (managed by `uv`).
- **Framework:** FastAPI (async, native OpenAPI, SSE for live updates).
- **Persistence:** SQLAlchemy 2.0 + Alembic migrations (DB engine → [04](04-database-sqlite.md)).
- **Validation:** Pydantic v2 / pydantic-settings.
- **Quality gate:** ruff (lint + format) + basedpyright (strict) + pytest — enforced by the shared `.claude` hooks.
- **Architecture:** modular monolith organized **by domain** (vertical slices), each slice `router.py → service.py → repository.py` + `schemas.py`/`models.py` — TBM's layering.
- **APIs:** REST (`/api/v1`) + **OPDS 1.2**; SSE for progress/scan events.

**Media-specific libraries** (to be pinned during implementation, per [07-image-decoding](../07-image-decoding.md)):
- Archives: `zipfile` (CBZ), `rarfile`/`libarchive-c` (CBR/7z), `pymupdf` (PDF), `ebooklib` (EPUB).
- Images: `pyvips` (primary decode/resize) + `Pillow`/`pillow-heif` (fallback/coverage).
- Container sniffing: `python-magic`. Natural sort: `natsort`. Fast hashing: `xxhash`.

**Background jobs:** a persisted queue is required (scans, thumbnails, imports). Decided in [08](08-task-runner.md): a **custom SQLite-backed queue + APScheduler** (broker-less), with priority + per-series group serialization (Komga's model).

## Consequences

- Inherits TBM conventions, hooks, and developer muscle memory.
- Async concentrated where it pays (page streaming, scanning); plain sync CRUD elsewhere — the media/scan path is the slow, I/O-bound dependency here (analogous to TBM's provider/LLM path).
- A clean REST+OPDS API makes the frontend and third-party clients (Tachiyomi/Mihon, KOReader, OPDS readers) all "just clients".

## Alternatives considered (from research)

- **Kotlin/Spring Boot (Komga):** the most capable reference, but heavyweight and not the house stack.
- **Crystal/Kemal (Mango), Perl/Mojolicious (LANraragi):** niche runtimes, small ecosystems.
- **C#/.NET (KamiYomu):** capable but not the house stack; also its LiteDB choice lacks migrations.
