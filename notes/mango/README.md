# Mango — Deep-Dive Code Analysis

> Analysis target: `temp/Mango` (v0.27.0, MIT)
> Analysis date: 2026-07-23
> Purpose: Inform architecture of **lychee** (Python 3.14 / FastAPI / SQLAlchemy / SQLite)

---

## Quick Facts

| Property | Value |
|---|---|
| Language | Crystal 1.0.0 |
| Web framework | Kemal 1.0.0 |
| Database | SQLite via crystal-sqlite3 0.18.0; migrations via `mg` 0.5.0 |
| Archive handling | ZIP/CBZ via Crystal stdlib; RAR/CBR/others via `archive.cr` 0.5.0 (libarchive bindings) |
| Image dimension reading | `image_size.cr` 0.5.0 |
| Thumbnail storage | Binary BLOBs in SQLite `thumbnails` table |
| Progress storage | Per-title `info.json` files on disk (not in DB) |
| API | Ad-hoc JSON REST + OpenAPI spec via `koa` shard + basic OPDS v1 catalog |
| Auth | Session cookies (kemal-session) + HTTP Basic Auth for OPDS; optional auth-proxy-header pass-through |
| Plugin engine | JavaScript via `duktape.cr` 1.0.0 (Duktape JS engine) |
| Concurrency model | Crystal fibers + channels; SQLite operations forced onto main fiber on ARM |
| Static assets | Embedded in binary at release build via `baked_file_system`; served from disk in dev |

**TL;DR.** Mango is a single-binary Crystal server. The library model is filesystem-first: one root `library_path`, subdirectories become Titles, archive files (`.cbz`/`.cbr`/`.zip`/`.rar`) or image-filled subdirs become Entries. Reading progress lives in per-directory `info.json` files. SQLite stores only IDs, thumbnails (as BLOBs), tags, sort-title overrides, and user accounts. The plugin system runs user-supplied JavaScript inside an embedded Duktape VM for scraping/downloading from external sites. OPDS support is catalog-only (no progress sync). No Tachiyomi/KOReader/OPDS-PS integration.

---

## 1. Stack

### Crystal & key shards

`shard.yml` specifies `crystal: 1.0.0`. Key production shards (from `shard.lock`):

| Shard | Version | Role |
|---|---|---|
| `kemal` | 1.0.0 | HTTP framework (routing, middleware, ECR templates) |
| `kemal-session` | 1.0.0 | Cookie sessions (365-day timeout, configured in `src/server.cr:50`) |
| `crystal-sqlite3` (as `sqlite3`) | 0.18.0 | SQLite driver |
| `archive.cr` | 0.5.0 | libarchive bindings for RAR/CBR and other non-ZIP archives |
| `image_size.cr` | 0.5.0 | Image dimension reading + thumbnail resize |
| `mg` | 0.5.0 | DB migrations (applied at startup via `MG::Migration.new(db).migrate`) |
| `duktape.cr` | 1.0.0 | Embeds Duktape JS engine for plugin execution |
| `myhtml` | 1.5.8 | HTML parsing exposed to plugin JS |
| `koa` | 0.9.0 | OpenAPI spec generation (produces `/openapi.json`) |
| `baked_file_system` | 0.10.0 | Embeds public/ assets into the binary at release compile |
| `clim` | 0.17.1 | CLI subcommand parsing (`mango admin user ...`) |
| `tallboy` | 0.9.3 | Table rendering for CLI output |
| `http_proxy` | 0.8.0 | HTTP proxy support for plugin downloads |
| `sanitize` | 0.1.0 | HTML sanitization |
| `kilt` | 0.4.1 | Template engine (ECR) |

### Database access layer & migrations

Raw SQL via `crystal-db` + `crystal-sqlite3`. No ORM. All queries are hand-written strings in `src/storage.cr`. The `mg` library runs numbered migration classes from `migration/*.cr` at every startup (`src/storage.cr:42-46`).

Migration sequence (numbered by filename):
1. `users.1.cr` — creates `users` table
2. `ids.2.cr` — creates original `ids` table (both entries + titles in one table)
3. `thumbnails.3.cr` — creates `thumbnails` table
4. `tags.4.cr` — creates `tags` table
5. `titles.5.cr` — splits `ids` into `ids` (entries only) + `titles`; migrates data
6. `foreign_keys.6.cr` — adds FK constraints (tags→titles, thumbnails→ids)
7. `ids_signature.7.cr` — adds `signature TEXT` column to `ids`
8. `relative_path.8.cr` — converts absolute paths to relative in both tables
9. `unavailable.9.cr` — adds `unavailable INTEGER DEFAULT 0` to both tables
10. `relative_path_fix.10.cr` — removes erroneous leading `/` from relative paths (bug fix for migration 8)
11. `md_account.11.cr` — creates `md_account` table for MangaDex OAuth tokens
12. `sort_title.12.cr` — adds `sort_title TEXT` column to both `ids` and `titles`

### Background jobs / scheduling

Mango uses Crystal fibers (`spawn`) for all background work. There is no external job queue or scheduler library. The `Queue` class in `src/queue.cr` is a SQLite-backed task list specifically for plugin downloads, polled by `Downloader` subclasses every second.

Background fiber jobs registered in `Library#register_jobs` (`src/library/library.cr:93-118`):
- **Library scan fiber**: runs `Library#scan` in a loop with `sleep scan_interval_minutes.minutes` (default 5 minutes). If `scan_interval_minutes < 1`, scans once synchronously and does not loop.
- **Thumbnail generation fiber**: sleeps 1 minute, then calls `Library#generate_thumbnails`, then sleeps `thumbnail_generation_interval_hours.hours` (default 24 hours).

Plugin update checking (`src/plugin/updater.cr:6-12`):
- `Plugin::Updater` spawns a fiber that loops over all plugins, checks subscriptions, and sleeps `plugin_update_interval_hours.hours` (default 24 hours).

Download worker (`src/queue.cr:14-27`):
- `Queue::Downloader` spawns a fiber that polls `pop` every second and calls `download(job)` when a job is found.

### ARM workaround: MainFiber

`src/main_fiber.cr` implements `MainFiber` — a channel-based trampoline that forces SQLite operations to run on the main fiber. This works around a crystal-sqlite3 crash on ARM (`crystal-lang/crystal-sqlite3#30`). Every `Storage` method wraps its DB access in `MainFiber.run { ... }`. This has a significant concurrency cost: each DB call is serialized through a channel send + receive round-trip.

### API style

Two API surfaces:
1. **JSON REST** at `/api/*` (non-RESTful by the developer's own admission in `src/routes/api.cr:22`). An OpenAPI spec is auto-generated and served at `/openapi.json`. Documented with the `koa` shard.
2. **OPDS v1 catalog** at `/opds` and `/opds/book/:title_id` — catalog-only (XML), no OPDS-PS.

### Auth / users

- `users` table: `(username TEXT, password TEXT, token TEXT, admin INTEGER)`
- Passwords: bcrypt via Crystal stdlib `Crypto::Bcrypt::Password`
- Sessions: kemal-session cookie (`mango-sessid-{port}`), stores `token` string
- Token: random UUID (without dashes) assigned at first login, stored in DB
- Admin flag: integer 0/1 in `users.admin`
- Three auth modes (checked in `AuthHandler#call`, `src/handlers/auth_handler.cr`):
  1. Session token cookie
  2. HTTP Basic Auth (for OPDS) or Bearer token header
  3. Auth-proxy header pass-through (`auth_proxy_header_name` config)
  4. Login-disabled mode (`disable_login = true`, uses `default_username`)
- MangaDex OAuth token stored in `md_account` table: `(username, token, expire)`

### Build & dev run

```
make run    # crystal run src/mango.cr --error-trace   (dev, interpreted)
make build  # crystal build src/mango.cr --release     (production binary)
make static # fully static binary for Alpine/Docker
make test   # crystal spec
```

Frontend assets: NPM + Gulp/Uglify. `make uglify` bundles JS; in release mode the `public/` dir is embedded via `baked_file_system`.

### Docker

Multi-stage build (`Dockerfile`). Builder stage: `crystallang/crystal:1.0.0-alpine`. Production image: `library/alpine`. The binary is fully static (Alpine requires `--static`). ARM variants have their own Dockerfiles (`Dockerfile.arm32v7`, `Dockerfile.arm64v8`).

### Relevance to lychee

**Adopt:** The `mg`-style numbered migration files (easy to port to Alembic). The config precedence (config file > env var > default) is clean; replicate with Pydantic settings. The MainFiber pattern is a Crystal-specific workaround — SQLAlchemy's async session + FastAPI's async handlers solve this cleanly. **Avoid:** Embedding thumbnails as BLOBs in SQLite (prefer filesystem paths). The lack of an ORM (hand-written SQL for every query) is tedious to maintain; SQLAlchemy models will be a large improvement.

---

## 2. Media Management Model

### Entity hierarchy

```
Library  (singleton, root directory)
└── Title  (subdirectory, recursive)
    ├── Title  (nested subdirectory)
    │   └── Entry ...
    └── Entry  (archive file OR image-directory)
        └── Pages  (images inside the archive/dir)
```

### Library (`src/library/library.cr`)

- Singleton accessed via `Library.default`
- Properties: `dir : String` (library_path), `title_ids : Array(String)`, `title_hash : Hash(String, Title)`
- Contains only top-level Titles (no Entries directly at library root)
- Serialized to gzipped YAML cache (`library_cache_path`, default `~/mango/library.yml.gz`)

### Title (`src/library/title.cr`)

A Title maps 1:1 to a filesystem directory. Key properties:

| Property | Type | Source |
|---|---|---|
| `id` | `String` | Random UUID (without dashes), persisted in `titles` table |
| `dir` | `String` | Absolute path to directory |
| `parent_id` | `String` | ID of parent Title; empty string = root |
| `title` | `String` | `File.basename(dir)` — directory name, verbatim |
| `signature` | `UInt64` | `Dir.signature(dir)` = CRC32 of sorted inodes (see §3) |
| `mtime` | `Time` | Max mtime across self + all nested entries and titles |
| `title_ids` | `Array(String)` | IDs of direct child Titles |
| `entries` | `Array(Entry)` | Direct child Entries (sorted by ChapterSorter) |

Display name (separate from `title`): read from `info.json` in the directory (`TitleInfo#display_name`, `src/library/types.cr:83`). Falls back to directory name if absent or empty.

Sort title: read from `titles.sort_title` DB column, falls back to `title` if null (`Title#sort_title`, `src/library/title.cr:351-361`).

Tags: stored in `tags` table, only for Titles (not Entries).

Cover URL: first entry's cover, overridable in `info.json` (`cover_url` field) or by uploading a file via `/api/admin/upload/cover`.

### Entry (abstract, `src/library/entry.cr`)

Abstract base class; two concrete subtypes:

#### ArchiveEntry (`src/library/archive_entry.cr`)

Maps to a single archive file (`.cbz`, `.zip`, `.cbr`, `.rar`). Key properties:

| Property | Source |
|---|---|
| `id` | Random UUID, persisted in `ids` table |
| `zip_path` | Absolute path to archive file |
| `title` | `File.basename(zip_path)` without extension |
| `size` | Human-readable file size (`File.size.humanize_bytes`) |
| `pages` | Count of image entries inside the archive |
| `mtime` | `File.info(zip_path).modification_time` |
| `signature` | `File.signature(zip_path)` = inode number |

#### DirEntry (`src/library/dir_entry.cr`)

Maps to a directory that contains only images (no sub-directories). Used when individual pages are stored as loose files. Key properties:

| Property | Source |
|---|---|
| `id` | Random UUID, persisted in `ids` table |
| `dir_path` | Absolute path to directory |
| `title` | `File.basename(dir_path)` |
| `pages` | Count of supported image files |
| `signature` | SHA1 of sorted inode numbers of image files |

A directory becomes a DirEntry if `DirEntry.is_valid?(path)` returns true, i.e., it contains at least one supported image file. A directory also gets scanned as a Title if it contains any supported archive files or other subdirectories. A directory can simultaneously be recognized as both a Title (containing entries as children) and a DirEntry of its parent Title — the checks are independent (`src/library/title.cr:55-62`).

### One-shots vs multi-entry

No special model for one-shots. A one-shot is simply a Title with one Entry. The UI code (`library.cr:310-322`) avoids showing nested titles in "start reading" to prevent weird UX (e.g., recommending Vol. 2 before Vol. 1 is read).

### Relationship summary

- `Library` → `Title` (1:N, top level only)
- `Title` → `Title` (1:N, recursive via `parent_id`)
- `Title` → `Entry` (1:N, via `entries` array; both ArchiveEntry and DirEntry)
- Tags: `titles.id` → `tags` table (M:N style, one row per tag)
- Thumbnails: `ids.id` → `thumbnails` table (1:1 per entry)
- Progress: stored in `info.json`, not in DB

### Relevance to lychee

**Adopt:** The three-level hierarchy (Library / Title / Entry) maps well to SQLAlchemy models. The Title = directory, Entry = archive/dir-of-images abstraction is clean and worth replicating. **Adapt:** Move progress tracking from JSON files to a DB table (cleaner, queryable, easier multi-user). Consider a separate `MediaItem` model for pages if you need to track individual pages with metadata.

---

## 3. File Management & Sync

### Scan pipeline

`Library#scan` (`src/library/library.cr:182-241`) runs on startup (after loading cache) and every N minutes in a fiber loop.

Step-by-step:

1. **List library root**: `Dir.entries(library_path)` filtered to non-hidden entries.
2. **Examine existing titles**: For each title in `title_ids`, call `title.examine(context)`:
   - If directory no longer exists → return `false`, mark for deletion.
   - Compute `Dir.contents_signature(dir)` (see below). If unchanged → return `true` (reuse cached title object, no rescan).
   - If changed → re-examine all child titles and entries recursively, adding/removing as needed.
3. **Add new titles**: Directories found in step 1 that are not in existing titles are constructed with `Title.new(path, "", cache)`. Titles with zero entries and zero sub-titles are discarded.
4. **Sort new titles**: `sort! { |a, b| a.sort_title <=> b.sort_title }` using `compare_numerically`.
5. **Bulk insert IDs**: All new IDs collected during scan are inserted in one DB transaction (`storage.bulk_insert_ids`, `src/storage.cr:319-343`).
6. **Mark unavailable**: `Storage#mark_unavailable` checks remaining DB rows against filesystem, sets `unavailable=1` for missing paths.
7. **Save library cache**: serializes Library to gzipped YAML in a spawned fiber.

### Content signature (change detection)

`Dir.contents_signature(dirname, cache)` (`src/util/signature.cr:57-79`):
- Recursively builds an array of filenames for all supported archive/image files.
- Computes `Digest::SHA1.hexdigest(sorted_filenames.join)`.
- Result is cached in `cache : Hash(String, String)` during a single scan to avoid re-scanning shared subdirectories.
- **Does NOT check file content or mtime** — only file existence and naming. Adding, deleting, or renaming a file triggers a rescan; editing a file's content does not.

### File identity (ID persistence across moves/renames)

Mango uses inode numbers as "signatures" to track files across renames/moves.

**For archive files** (`File.signature`, `src/util/signature.cr:21-28`):
- Returns `File.info(filename).inode` if it is a supported archive or image file.
- Returns `0` otherwise.

**For title directories** (`Dir.signature`, `src/util/signature.cr:33-50`):
- Recursively collects inodes of all files and subdirs.
- Computes `Digest::CRC32.checksum(sorted_inodes.join)` → `UInt64`.

**For directory entries** (`Dir.directory_entry_signature`, `src/util/signature.cr:82-95`):
- SHA1 of sorted inode numbers of all image files in the directory.

### ID lookup / matching (`src/storage.cr:227-309`)

Three-step fallback for both entries and titles:

1. **Exact match**: `WHERE path = ? AND signature = ? AND unavailable = 0` → found? Use it and update if needed.
2. **Path-only match**: `WHERE path = ?` → handles case where archive was edited (inode unchanged but signature differs) or new files were added to a title.
3. **Signature-only match with path similarity**: `WHERE signature = ?` → finds all candidates, picks the one with the highest path component similarity (components_similarity, `src/util/util.cr:154-162`) → handles rename/move without losing progress.

If no match: generate new UUID, queue for bulk insert.

The "path similarity" heuristic (`String#components_similarity`) compares path components backward (trailing components first), normalised by length of shorter path. Example: `/lib/A/B/ch1.cbz` vs `/lib/C/B/ch1.cbz` would have high similarity because they share the `B/ch1.cbz` suffix.

### File watching

**None.** Mango uses only periodic polling (configurable via `scan_interval_minutes`). No inotify, FSEvents, or kqueue. Setting `scan_interval_minutes < 1` disables periodic scanning and runs a single scan at startup.

### Orphan/missing handling

- After scan, `Storage#mark_unavailable` is called with the IDs of deleted items.
- Rows with `unavailable=1` are excluded from normal ID lookups.
- They remain in DB and are queryable via `/api/admin/entries/missing` and `/api/admin/titles/missing`.
- Admin can delete them via `/api/admin/entries/missing/:eid` (DELETE) or bulk delete.

### Library cache

A gzipped YAML serialization of the entire `Library` object tree (including all Titles and Entries with their in-memory state) is written to `library_cache_path` after every scan. On startup, if the cache file exists, it is loaded first (`Library.load_instance`, `src/library/library.cr:48-78`), then a scan runs to update it.

Safety checks on load: directory mismatch (cached `dir != config.library_path`) or count inconsistency (cache has titles, DB has none) → delete cache and restart.

### In-memory LRU cache (`src/library/cache.cr`)

A size-bounded in-memory cache (`LRUCache`) stores:
- Sorted entry arrays (`SortedEntriesCacheEntry`): keyed by SHA1 of (book_id + entry_ids + username + sort_options)
- Sorted title arrays (`SortedTitlesCacheEntry`): keyed by SHA1 of (title_ids + username + sort_options)
- `info.json` contents (as JSON string): keyed by `"${dir}:info.json"`
- Progress sums (SHA1-signed): keyed by `"${id}:${username}:progress_sum"`

Default size: 50 MB (configurable via `cache_size_mbs`). Eviction: LRU (least recently accessed entry removed when limit exceeded).

### Relevance to lychee

**Adopt:** The 3-step ID lookup fallback (path+signature, path-only, signature+similarity) is brilliant for handling user file operations without losing reading progress. Port this to SQLAlchemy with inode as an integer column. **Adapt:** Replace periodic polling with inotify/FSEvents for better latency (Python: `watchfiles` or `watchdog`). Consider also watching for content changes (mtime check) not just structural changes. **Avoid:** The YAML library cache is fragile (cache/DB mismatch crashes Mango, requires manual restart). Use a DB-first model where the DB is always the source of truth.

---

## 4. Reading Tracker

### Progress storage model

Reading progress is **not stored in SQLite**. It lives in `info.json` files on disk, inside each Title's directory.

`TitleInfo` class (`src/library/types.cr:77-132`):

```
info.json structure:
{
  "comment": "Generated by Mango. DO NOT EDIT!",
  "display_name": "...",
  "entry_display_name": { "chapter1.cbz": "Chapter 1" },
  "cover_url": "",
  "entry_cover_url": { "chapter1.cbz": "/uploads/img/abc.png" },
  "progress": {
    "alice": { "Chapter 1": 12, "Chapter 2": 0 },
    "bob":   { "Chapter 1": 5 }
  },
  "last_read": {
    "alice": { "Chapter 1": "2024-01-15T10:30:00Z" }
  },
  "date_added": { "Chapter 1": "2023-11-01T09:00:00Z" },
  "sort_by": {
    "alice": ["title", true]
  }
}
```

Key decisions:
- Progress keyed by **entry title** (filename without extension), not by entry ID. This is explicitly noted as backward compatibility with v0.1.0 (`src/library/entry.cr:142`).
- Page number is an integer (current page, 1-indexed; 0 = not started; `pages` = completed).
- `load_progress` caps at `entry.pages` to handle rounding from re-archiving (`src/library/entry.cr:174`).
- `finished?` = `load_progress == pages`.

Progress write path (`Entry#save_progress`, `src/library/entry.cr:142-163`):
1. Invalidates LRU cache entries (progress sum, sorted entries by progress).
2. Opens `info.json` via `TitleInfo.new(book.dir)` (mutex-protected per directory).
3. Writes new progress and last_read timestamp.
4. Calls `info.save` which writes `info.to_pretty_json` to disk.

Reading progress for the entire title (`Title#read_all`/`#unread_all`, `src/library/title.cr:493-504`): iterates all entries and sets progress to `pages` (read) or 0 (unread).

### Multi-user

Full per-user progress, last_read, sort preferences, and display names (the latter is admin-only to set). The `info.json` hash uses username as a top-level key for progress, last_read, and sort_by.

### External sync

**None.** OPDS support is catalog-only (title/entry listing, no OPDS-PS progress sync). No Tachiyomi/Mihon sync, no KOReader opds, no Komga-compatible API.

### Home page sections

Three sections computed in `Library` (`src/library/library.cr:243-321`):
1. **Continue reading**: last in-progress entry per title, sorted by last_read descending.
2. **Recently added**: entries added within the last month, grouped by title if multiple added on the same day.
3. **Start reading**: random sample of titles where reading percentage = 0.

### Relevance to lychee

**Adopt:** The three home sections (continue reading, recently added, start reading) are excellent UX. **Avoid entirely:** Storing progress in `info.json` — it conflicts with the DB being the source of truth, is not queryable, breaks if files are deleted and re-scanned with new titles, and creates write-contention under concurrent users. Use a `reading_progress` table: `(user_id, entry_id, current_page, total_pages, last_read_at, completed_at)`. **Adopt with adaptation:** The entry-level progress model (current page / total pages) is the right granularity. Consider adding a `completed` boolean column separate from `current_page == total_pages` for cases where pages change after archiving.

---

## 5. Metadata & Tagging

### Metadata model

Metadata is split between SQLite (IDs, sort titles, tags, thumbnails) and `info.json` files (display names, cover overrides, progress, date added).

#### SQLite tables (final schema after all migrations)

**`users`**:
```sql
username TEXT NOT NULL  (UNIQUE)
password TEXT NOT NULL  (bcrypt hash)
token    TEXT           (UNIQUE, session token)
admin    INTEGER NOT NULL
```

**`titles`**:
```sql
id          TEXT NOT NULL  (UNIQUE, random UUID)
path        TEXT NOT NULL  (UNIQUE, relative to library_path)
signature   TEXT           (CRC32 of sorted inodes as string)
unavailable INTEGER NOT NULL DEFAULT 0
sort_title  TEXT           (NULL = use title/dirname)
```

**`ids`** (entries):
```sql
path        TEXT NOT NULL  (UNIQUE, relative to library_path)
id          TEXT NOT NULL  (UNIQUE, random UUID)
signature   TEXT           (inode number as string)
unavailable INTEGER NOT NULL DEFAULT 0
sort_title  TEXT           (NULL = use entry title)
```

**`thumbnails`**:
```sql
id       TEXT NOT NULL  (UNIQUE, FK → ids.id ON DELETE CASCADE)
data     BLOB NOT NULL  (raw image bytes)
filename TEXT NOT NULL
mime     TEXT NOT NULL
size     INTEGER NOT NULL  (bytes)
```

**`tags`**:
```sql
id  TEXT NOT NULL  (FK → titles.id ON DELETE CASCADE)
tag TEXT NOT NULL
UNIQUE(id, tag)
```

**`md_account`**:
```sql
username TEXT NOT NULL PRIMARY KEY  (FK → users.username)
token    TEXT NOT NULL
expire   INTEGER NOT NULL  (Unix timestamp)
```

**`queue`** (separate DB file at `queue_db_path`):
```sql
id             TEXT  (UNIQUE; format: "${plugin_id}-${base64(chapter_id)}" for plugins)
manga_id       TEXT
title          TEXT
manga_title    TEXT
status         INTEGER  (0=Pending, 1=Downloading, 2=Error, 3=Completed, 4=MissingPages)
status_message TEXT
pages          INTEGER
success_count  INTEGER
fail_count     INTEGER
time           INTEGER  (Unix timestamp milliseconds)
```

#### `info.json` metadata (per title directory)

Fields (all optional, all have defaults):
- `display_name`: Override for the title's displayed name (fallback: dirname)
- `entry_display_name`: `{filename → display_name}` map for per-entry display names
- `cover_url`: Override cover URL for the title
- `entry_cover_url`: `{filename → url}` map for per-entry cover overrides
- `progress`: `{username → {entry_title → page_number}}`
- `last_read`: `{username → {entry_title → ISO8601 timestamp}}`
- `date_added`: `{entry_title → ISO8601 timestamp}` (populated lazily using file ctime)
- `sort_by`: `{username → [method_string, ascend_bool]}`

### Tags

Only on Titles (not Entries). The `tags` table stores `(title_id, tag)` pairs. Operations:
- `Storage#add_tag(id, tag)` / `Storage#delete_tag(id, tag)`
- `Storage#get_title_tags(id)` → sorted array of tag strings
- `Storage#list_tags` → distinct tags for non-unavailable titles

Tags are exposed via the admin API (`PUT/DELETE /api/admin/tags/:tid/:tag`) and the tags view.

### Display name & sort title

- **Display name**: set via `PUT /api/admin/display_name/:tid/:name`, persisted in `info.json`. Entry display names are keyed by entry filename (not ID).
- **Sort title**: set via `PUT /api/admin/sort_title/:tid`, stored in `titles.sort_title` or `ids.sort_title` DB columns. Used for sorting only; display is unchanged. Admin-only.

### Plugin/subscription metadata

When downloading via a plugin, the manga title and chapter title come from the plugin's `listChapters` / `selectChapter` JS functions. There is no metadata enrichment beyond what the plugin returns. The plugin system does not write to `info.json`.

### Search/filter/sort

- **Search**: no full-text search. Filtering is only via tags (click a tag → browse all titles with that tag).
- **Sort** (per user, per title/library): 5 methods:
  - `Auto` (ChapterSorter — smart chapter ordering)
  - `Title` (compare_numerically on sort_title)
  - `Progress` (reading completion percentage)
  - `TimeModified` (mtime)
  - `TimeAdded` (date_added from info.json)
  - Each with Ascending/Descending variant, saved to `info.json` `sort_by` field per user.

### Relevance to lychee

**Adopt:** The title/entry display_name + sort_title split (display vs. sort are independent) is clean. **Avoid:** Storing tags only on titles and not entries limits utility. **Adapt:** Move all metadata (display names, tags, date_added) into SQLite rather than splitting across DB + JSON files. JSON-file metadata creates write-concurrency issues and makes queries impossible. Implement full-text search from day one (SQLite FTS5). Add per-entry tags as well as per-title tags. Consider OPDS `dc:language`, `dc:publisher`, `dc:creator` metadata fields for Komga compatibility.

---

## 6. Media Scan & Filename Structure

### Expected directory layouts

**Standard manga (multi-volume)**:
```
library/
  One Punch Man/
    Vol. 1/
      Ch. 001 - Strongest Man.cbz
      Ch. 002 - Lone Cyborg.cbz
    Vol. 2/
      Ch. 009 - Terrifying City.cbz
    info.json
```

**Simple flat manga**:
```
library/
  Berserk/
    Berserk v01.cbz
    Berserk v02.cbz
    Berserk v03.cbz
```

**Directory-as-entry (loose images)**:
```
library/
  My Manga/
    Chapter 1/
      page001.jpg
      page002.jpg
    Chapter 2/
      page001.jpg
```

**Mixed** (a Title can simultaneously contain sub-Titles AND direct Entries):
```
library/
  Manga/
    bonus_chapter.cbz        ← direct ArchiveEntry of "Manga"
    Manga Vol. 1/
      ch01.cbz               ← ArchiveEntry of "Manga Vol. 1"
```

### Scan pipeline (step by step)

The `Title` constructor (`src/library/title.cr:27-81`) and `Title#examine` (`src/library/title.cr:92-219`) implement the scan:

1. Compute `Dir.signature(dir)` → CRC32 of sorted inodes. Look up/register in `titles` table.
2. Compute `Dir.contents_signature(dir, cache)` → SHA1 of sorted filenames (recursive). Store as `@contents_signature`.
3. Iterate `Dir.entries(dir)`, skipping hidden files (starting with `.`):
   a. If subdirectory:
      - Recursively construct `Title.new(path, @id, cache)` for nested Title.
      - If the nested Title has zero entries AND zero sub-titles, discard it.
      - Also check `DirEntry.is_valid?(path)`: if it has images, create a `DirEntry` for the parent.
   b. If file with supported extension (`.zip`, `.cbz`, `.rar`, `.cbr`):
      - Construct `ArchiveEntry.new(path, self)`.
      - If `pages == 0` and no `err_msg`, discard (empty or unreadable archive).
4. Compute `@mtime` as max(self.mtime, all child title mtimes, all entry mtimes).
5. Sort child titles: `compare_numerically` on title name.
6. Sort entries: `ChapterSorter` (see below).

On re-examine (`Title#examine`):
1. Return `false` if directory no longer exists.
2. Recompute `contents_signature`; return `true` if unchanged (short-circuit).
3. Re-examine all child titles and entries recursively.
4. Add new files/dirs found since last scan.
5. Remove deleted files/dirs.
6. Re-sort if any additions or deletions occurred.
7. Return `false` if both `title_ids` and `entries` are empty after cleanup.

### Filename/folder parsing

**Title name**: `File.basename(dir)` — the directory name, verbatim. No parsing.

**Entry title**: `File.basename(path)` without extension. No parsing for volume/chapter numbers.

**Sorting of entries** (`ChapterSorter`, `src/util/chapter_sort.cr`):
- Scans all entry titles to find numeric patterns: regex `([^0-9\n\r\ ]*)[ ]*([0-9]*\.*[0-9]+)`.
- Builds a table of "keys" (string prefix before a number, e.g., `"Vol."`, `"Ch."`, `""`) with value ranges and frequency counts.
- Keys appearing in fewer than half the entries are discarded.
- Keys sorted by frequency (desc) then value range (desc).
- For each pair (a, b), comparison iterates keys: if both have the key, compare numerically; if only one has it, it sorts after.
- Handles decimal numbers (e.g., "Ch. 10.5") via `BigDecimal`.

**Sorting of titles/images**: `compare_numerically` (`src/util/numeric_sort.cr:40-42`):
- Splits string into alternating alpha and numeric segments.
- Compares segment-by-segment: numeric segments compared as `BigInt`, alpha segments compared lexicographically.
- Example: `"ch2"` sorts before `"ch10"`.

### Special handling of nested titles

A directory is scanned for both sub-Title and DirEntry potential simultaneously. The critical code in `Title#initialize` (`src/library/title.cr:47-62`):

```crystal
if File.directory? path
  title = Title.new path, @id, cache      # always try as nested Title
  unless title.entries.size == 0 && title.titles.size == 0
    Library.default.title_hash[title.id] = title
    @title_ids << title.id
  end
  if DirEntry.is_valid? path              # also try as DirEntry of current title
    entry = DirEntry.new path, self
    @entries << entry if entry.pages > 0 || entry.err_msg
  end
  next
end
```

This dual-recognition means a directory can be both a child Title (for further navigation) and an Entry (for reading as a flat image sequence) of the same parent.

### Relevance to lychee

**Adopt:** The `ChapterSorter` algorithm is sophisticated and handles real-world manga naming conventions well. Port the algorithm to Python. **Adopt:** The dual Title+Entry recognition for directories. **Adapt:** Consider also parsing CBZ/CBR metadata (`ComicInfo.xml` inside archives is the de facto standard for Komga/Kavita compatibility) to extract richer metadata. **Avoid:** The "title name = directory name" restriction — lychee should support an explicit `title` field in a sidecar `lychee.json` or `ComicInfo.xml`.

---

## 7. Image Decoding & Archives

### Container formats

Supported archive extensions defined in `src/util/util.cr:6`:
```crystal
SUPPORTED_FILE_EXTNAMES = [".zip", ".cbz", ".rar", ".cbr"]
```

`ArchiveFile` class (`src/archive.cr`) unifies two backends:
- **ZIP/CBZ**: Crystal standard library `Compress::Zip::File` — used when extension is `.cbz` or `.zip`.
- **RAR/CBR and others**: `archive.cr` 0.5.0 — `Archive::File` from libarchive bindings — used for all other extensions.

```crystal
def initialize(@filename : String)
  if [".cbz", ".zip"].includes? File.extname filename
    @archive_file = Compress::Zip::File.new filename
  else
    @archive_file = Archive::File.new filename
  end
end
```

Archive validation (`validate_archive`) is called during `ArchiveEntry` construction; on failure, `@err_msg` is set and the entry is kept (shown with error UI) if `err_msg` is set, or discarded if `pages == 0` and no error.

**No support for**: 7-Zip (`.7z`), PDF, EPUB, folder-zips with nested archives.

### Image formats

```crystal
SUPPORTED_IMG_TYPES = %w(
  image/jpeg image/png image/webp image/apng
  image/avif image/gif image/svg+xml image/jxl
)
```

Detection is by MIME type from filename extension (`MIME.from_filename?`), not by file content magic bytes.

### Page ordering inside archives

`ArchiveEntry#sorted_archive_entries` (`src/library/archive_entry.cr:52-64`):
1. Lists all entries in the archive.
2. Filters to supported image MIME types.
3. Sorts by filename using `compare_numerically` (natural numeric sort).

This means a CBZ with files `page1.jpg`, `page10.jpg`, `page2.jpg` will be ordered `page1`, `page2`, `page10`. Directory structure inside the archive is ignored during page ordering — only the filename (not the full path) determines sort order. Inference: files in subdirectories inside an archive would all be mixed together after filtering.

### Page extraction

`ArchiveEntry#read_page(page_num)` (`src/library/archive_entry.cr:66-82`):
1. Calls `sorted_archive_entries` (opens archive each time).
2. Reads `entries[page_num - 1]` from the sorted list.
3. Returns an `Image` struct with raw bytes, MIME type, filename, and size.
4. No caching of page data in memory (archives are re-opened per request).

`DirEntry#read_page(page_num)` (`src/library/dir_entry.cr:60-73`):
1. Gets sorted image file list.
2. Reads file at index `page_num - 1` via `File.read`.
3. Returns `Image` struct.

### Image dimensions

`entry.page_dimensions` opens the archive and calls `ImageSize.get(data)` on each page's raw bytes via `image_size.cr`. Returns `[{width: Int32, height: Int32}]`. Used by the reader's fit-to-width/height modes. Called lazily on demand (not cached).

### Thumbnail generation

`Entry#generate_thumbnail` (`src/library/entry.cr:200-223`):
1. Reads page 1 via `read_page(1)`.
2. Gets image dimensions via `ImageSize.get(img.data)`.
3. Resize heuristic:
   - Portrait (height > width): resize to `width: 200`
   - Landscape: resize to `height: 300`
4. Resize performed by `ImageSize.resize` from `image_size.cr`.
5. Non-WebP images are re-encoded as JPEG after resize (`img.mime = "image/jpeg"`).
6. Stores result in `thumbnails` table as BLOB via `Storage#save_thumbnail`.

Thumbnail retrieval (`Entry#get_thumbnail`):
- Queries `thumbnails` table by entry ID.
- Returns `nil` if not found (will fall through to reading page 1 live).

Cover endpoint (`GET /api/cover/:tid/:eid`, `src/routes/api.cr:168-196`):
```crystal
img = entry.get_thumbnail || entry.read_page 1
```

So covers always work even without pre-generation; generation just provides resized, cached versions.

Thumbnail generation scheduling: bulk generation runs after library scan in a fiber, sleeping 1 second between each entry (`library.cr:353-359`) to avoid saturating disk I/O. Progress reported via `Library#thumbnail_ctx`.

### Cover override

Admins can upload a custom cover image via `POST /api/admin/upload/cover`:
- File saved under `upload_path/img/{random}.{ext}`.
- URL path stored in `info.json` (`cover_url` or `entry_cover_url`).
- URL takes precedence over generated thumbnail.

### Corrupt/unreadable archive handling

`ArchiveEntry` constructor validates the archive (`validate_archive`). On failure:
- Sets `@err_msg = "Archive error: ..."`.
- Sets `@pages = 0` (initialized to 0 by allocate).
- Entry is added to the title if `err_msg` is set (shown with error indicator in UI).
- Entry is NOT added if `pages == 0 && err_msg.nil?` (empty but valid archive — silently dropped).

Corrupt archives remain in the library as visible-but-unreadable entries, which is a deliberate UX choice.

### ETag caching for page images

`GET /api/page/:tid/:eid/:page` (`src/routes/api.cr:125-159`):
- Computes ETag as `Digest::SHA1.hexdigest(img.data)`.
- Responds 304 if `If-None-Match` header matches.
- Sets `Cache-Control: public, max-age=86400` for archive entries.
- Sets `Cache-Control: no-cache, max-age=86400` for directory entries (content can change).

### Relevance to lychee

**Adopt:** The dual ZIP (stdlib) + libarchive (for RAR) backend strategy. In Python: `zipfile` stdlib for CBZ/ZIP, `rarfile` or `unrar-cffi` for CBR. **Adopt:** The thumbnail-on-demand fallback (`get_thumbnail || read_page(1)`). **Adopt:** 1-second sleep between thumbnail generations to reduce I/O impact. **Adapt:** Use filesystem paths (not BLOBs) for thumbnail storage — BLOBs bloat the SQLite file and prevent CDN/nginx caching. **Adopt:** ETag strategy for page images. **Adapt:** Add support for `ComicInfo.xml` inside archives (Komga/Kavita standard) for rich metadata extraction. **Add:** PDF support (not present in Mango), EPUB support.

---

## Notable Design Decisions, Tradeoffs & Gotchas

### Design decisions

1. **Filesystem-first**: Library structure is derived 100% from the filesystem. Adding a manga = drop files in the library dir; no import workflow required. Side effect: metadata is tied to directory names, which can't easily be changed without breaking scan consistency.

2. **info.json as progress store**: Avoids DB writes for the most frequent operation (page turn). Drawback: JSON files are not queryable, create write-contention under concurrent users, and require mutex locking per directory (`TitleInfo` uses a `Mutex` per directory, `src/library/types.cr:108-130`).

3. **Inode-based identity**: Using inode numbers to track files across renames is clever but fragile: inodes are not stable across remounts, device moves, or filesystem replacements. The 3-step fallback mitigates this.

4. **JavaScript plugin engine**: Running user JavaScript in Duktape is an interesting choice — plugins are portable text files, and the `mango` object exposes HTTP client + HTML parser + storage. Drawback: Duktape is ES5 only (no async/await, no modern JS), and the plugin ABI has two incompatible versions (v1 and v2).

5. **No watch / inotify**: Periodic polling is simpler to implement correctly across platforms but adds latency for new content.

6. **BLOB thumbnails in SQLite**: Stores image bytes in the DB. Simple to implement but: SQLite is not optimized for large blob access; the DB file grows unboundedly; browser caching via CDN/nginx is impossible.

7. **Single library**: Mango supports exactly one library directory. Multi-library is a frequently requested feature (per README notes) but not implemented.

8. **ARM MainFiber workaround**: The channel-based trampoline for SQLite on ARM is a creative workaround for a driver bug, but it serializes all DB access through a single channel, eliminating any possibility of concurrent DB queries.

### Pain points observed in code

- `info.json` write-contention: mutex per directory, but still requires disk write on every page turn. Under many concurrent readers this becomes a bottleneck.
- Signature computation is recursive and re-traverses the full directory tree every scan even when most content is unchanged.
- Thumbnail BLOBs: querying the DB for thumbnails loads potentially large blobs into memory for every cover request.
- Plugin JS is synchronous and single-threaded; long-running downloads block the download fiber.
- No search beyond tag filtering.
- `entry.date_added` is computed lazily and stored in `info.json`; it relies on `ctime` which is not preserved across copies/archives.

---

## File Index

All paths relative to `temp/Mango/`:

| File | Role |
|---|---|
| `src/mango.cr` | Entry point, CLI, initialization order |
| `src/server.cr` | Kemal server setup, middleware registration, router registration |
| `src/config.cr` | Config loading (YAML + env vars), all configurable options |
| `src/storage.cr` | All SQLite access; user management; ID lookup/insert; thumbnail storage; tag CRUD; unavailable tracking |
| `src/library/library.cr` | Library singleton; scan loop; thumbnail generation loop; home page sections |
| `src/library/title.cr` | Title model; examine; sort; info.json access; progress bulk operations |
| `src/library/entry.cr` | Abstract Entry; progress read/write; thumbnail generate/get |
| `src/library/archive_entry.cr` | ArchiveEntry (ZIP/RAR files); page reading |
| `src/library/dir_entry.cr` | DirEntry (image directories); page reading |
| `src/library/types.cr` | SortOptions, SortMethod enum, Image struct, TitleInfo (info.json), ExamineContext |
| `src/library/cache.cr` | LRUCache; SortedEntriesCacheEntry; SortedTitlesCacheEntry |
| `src/archive.cr` | ArchiveFile unified wrapper (Compress::Zip + archive.cr) |
| `src/queue.cr` | SQLite-backed download queue; Downloader base class |
| `src/plugin/plugin.cr` | Plugin loading, Duktape runtime, JS helper functions |
| `src/plugin/downloader.cr` | Plugin::Downloader; chapter download to CBZ |
| `src/plugin/updater.cr` | Plugin::Updater; subscription check loop |
| `src/plugin/subscriptions.cr` | Subscription, SubscriptionList, Filter types |
| `src/routes/api.cr` | All JSON API endpoints |
| `src/routes/opds.cr` | OPDS v1 catalog endpoints |
| `src/routes/main.cr` | Main HTML routes |
| `src/routes/reader.cr` | Reader HTML route |
| `src/routes/admin.cr` | Admin HTML routes |
| `src/handlers/auth_handler.cr` | Authentication middleware |
| `src/util/signature.cr` | File.signature, Dir.signature, Dir.contents_signature |
| `src/util/chapter_sort.cr` | ChapterSorter (smart chapter ordering) |
| `src/util/numeric_sort.cr` | compare_numerically (natural alphanumeric sort) |
| `src/util/util.cr` | Constants, MIME registration, sanitize_filename, sort_titles |
| `src/main_fiber.cr` | MainFiber (ARM SQLite workaround) |
| `src/rename.cr` | Rename rule DSL (for plugin download naming) |
| `migration/*.cr` | DB migration scripts (numbered 1–12) |
| `shard.yml` | Dependency declarations |
| `shard.lock` | Locked dependency versions |
| `Dockerfile` | Multi-stage Docker build (x86_64 Alpine) |
| `Makefile` | Build targets |
