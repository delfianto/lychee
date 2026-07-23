# LANraragi — Deep-Dive Architecture Notes

> Research notes for the **lychee** project. Every claim is backed by a source citation.

---

## Quick Facts

| Item | Value |
|------|-------|
| Language / Runtime | Perl 5.36+ |
| Web Framework | Mojolicious 9.39 |
| Datastore | Redis (5 logical databases; **no SQL**) |
| Background Jobs | Minion 10.x (Redis backend) |
| File Watcher | Shinobu (separate process, `lib/Shinobu.pm`) |
| Views | Template::Toolkit 2 (`.tt2` files) |
| Media Model | **Archive-centric**: one file = one entry; ID = SHA-1 of first 512 KB |
| Grouping | Tags + Categories (static/dynamic) + Tankoubon (ordered multi-archive collections) |
| Archive libs | `Archive::Libarchive` (ZIP/CBZ/RAR/CBR/7z/tar/lzma/…), `libvips` via FFI for PDF, proxy fetch for CBW |
| Thumbnail / resize | libvips (preferred) or ImageMagick; JPEG or JPEG XL output |
| Plugin system | `Module::Pluggable`: Metadata + Download + Login + Script plugin types |
| API | REST + OpenAPI 3 (`tools/openapi.yaml`), documented with Redocly |
| Auth | Single shared password (bcrypt) + API key (Bearer token) |
| Docker | Official image on `ghcr.io/difegue/lanraragi`; Redis bundled |
| Platforms | Linux (primary), macOS, Windows (partial — no MCE threading, limited libarchive) |

**TL;DR** — LANraragi is an archive/doujinshi server designed around a flat file-system of comic/manga archives. Its defining characteristic is that Redis is the entire database: every archive, category, tankoubon, tag index, search cache, and job queue lives in Redis. There is no SQL schema. Organization is via free-form tags (with namespaces), not a hierarchical series/volume tree. Grouping of related archives is done through Tankoubon (manually ordered) or dynamic categories (saved searches). Multi-page reading progress is tracked per archive as a single integer (current page). The plugin system enables automatic tag/metadata fetching from external sites.

---

## 1. Stack

### 1.1 Perl + Mojolicious

- **Language**: Perl 5.36.0 minimum (`tools/cpanfile` line 2).
- **Web framework**: `Mojolicious` 9.39 (`cpanfile` line 39). The app is a single `Mojolicious` class at `lib/LANraragi.pm`; routes are registered in `lib/LANraragi/Utils/Routing.pm`.
- **Views**: `Mojolicious::Plugin::TemplateToolkit` 0.005 (`cpanfile` line 40) renders `.tt2` templates in `templates/`.
- **OpenAPI**: `Mojolicious::Plugin::OpenAPI` 5.11 + `JSON::Validator` 5.19 (`cpanfile` lines 42–43); spec at `tools/openapi.yaml`; Redocly config at `redocly.yml`. All `/api/` routes are validated against the spec.

### 1.2 Redis as the Database

Redis is the **sole** persistent store. `lib/LANraragi/Model/Config.pm` defines five logical databases (line 37–49) and their `get_redis*` factory methods (lines 70–104).

```
lrr.conf:
  redis_database         => "0"   # archive hashes + tag indexes
  redis_database_minion  => "1"   # Minion job queue
  redis_database_config  => "2"   # app config + filemap + tagrules
  redis_database_search  => "3"   # search indexes + cache
  redis_database_metrics => "4"   # prometheus-style counters
```

Detailed key layout is in the companion file `redis-schema.md`.

Key design choices:
- Archive metadata lives in a Redis HASH keyed by SHA-1 ID.
- Search indexes are Redis SETs (`INDEX_<tag>`), a sorted set (`LRR_TITLES` for lexicographic title sort), and a sorted set for tag statistics (`LRR_STATS`).
- The search cache (`LRR_SEARCHCACHE`) is a Redis HASH of Perl-`Storable`-serialized result arrays; it is invalidated (deleted + recreated) on any metadata change via `invalidate_cache()` (`lib/LANraragi/Utils/Database.pm` line 615).
- No joins, no foreign keys, no transactions except optimistic `WATCH/MULTI/EXEC` blocks during full stat rebuilds (`lib/LANraragi/Model/Stats.pm` line 62).

### 1.3 Minion Job Queue

`Minion` 10.x with `Minion::Backend::Redis` (`cpanfile` lines 49–50). Registered tasks (all in `lib/LANraragi/Utils/Minion.pm`):

| Task | Description |
|------|-------------|
| `thumbnail_task` | Generate one cover or per-page thumbnail |
| `tank_thumbnail_task` | Copy first archive's first page as tankoubon cover |
| `page_thumbnails` | Batch-generate all per-page thumbnails (MCE parallel) |
| `regen_all_thumbnails` | Full thumbnail regeneration pass |
| `find_duplicates` | Hamming-distance duplicate detection on `thumbhash` fields |
| `build_stat_hashes` | Full index rebuild (flushes and rewrites DB 3) |
| `handle_upload` | Process a file upload |
| `download_url` | Download and import from URL via downloader plugins |
| `run_plugin` | Execute a metadata or script plugin on a single archive |
| `backup_json` | Serialize all metadata to JSON |
| `restore_backup` | Restore from a JSON backup |

The Minion worker process (`lib/Worker.pm`) runs as a separate process managed by `Proc::Simple` (`cpanfile` line 53). On Unix it uses `Sys::CpuAffinity` + `MCE::Loop` for parallel thumbnail work. Windows uses a single-threaded fallback.

### 1.4 Shinobu File Watcher

`lib/Shinobu.pm` — a separate Perl process launched at startup via `Proc::Simple`. It uses `File::ChangeNotify` 0.31 (`cpanfile` line 58) to listen for `create`/`modify`/`delete` events on the content directory, filtering for recognized archive extensions (line 88). On startup it performs a full scan (`update_filemap`), then enters an event loop polling every 1 second (line 106).

### 1.5 Key CPAN Modules

| Module | Role |
|--------|------|
| `Redis` 1.995 | Redis client |
| `Archive::Libarchive` 0.03/0.04 | Archive reading/extraction |
| `Archive::Zip` 1.68 | ZIP-specific (legacy path) |
| `Digest::SHA` 6.02 | SHA-1 ID computation |
| `File::ChangeNotify` 0.31 | Filesystem event watching (Shinobu) |
| `MCE::Loop`, `MCE::Shared` | Multi-core parallel processing (Minion tasks) |
| `Parallel::Loops` 0.10 | Parallel archive scanning |
| `Module::Pluggable` 5.2 | Plugin auto-discovery |
| `Sort::Naturally` 1.03 | Natural sort for page ordering |
| `CHI` 0.61 + `CHI::Driver::FastMmap` | In-process page cache (mmap on Unix) |
| `FFI::Platypus` 2.10 | Call into `libvips` for PDF rendering and image ops |
| `Mojo::UserAgent` (bundled) | HTTP client for CBW proxy and plugin fetches |
| `YAML::PP` 0.38 | YAML parsing (Ksk plugin) |
| `String::Similarity` 1.04 | String fuzzy match (Hentag plugin) |
| `Authen::Passphrase` 0.008 | bcrypt password check |

### 1.6 API Style

REST + OpenAPI 3.0 (`tools/openapi.yaml`). All `/api/` routes are declared with OpenAPI `operationId`s; the Mojolicious OpenAPI plugin validates request/response. Return format is JSON. Authentication: `Authorization: Bearer base64(<api_key>)` header OR `?key=<api_key>` query param OR session cookie (`lib/LANraragi/Utils/Login.pm` line 12). Progress updates can optionally require auth (`enable_authprogress` config flag). OPDS Atom feed is also supported (`lib/LANraragi/Model/Opds.pm`).

### 1.7 Auth

Single-tenant design. One shared password (bcrypt stored in `LRR_CONFIG.password`, default `kamimamita`). One shared API key (`LRR_CONFIG.apikey`). No per-user accounts. Password protection can be disabled (`enablepass = 0`). There is a "no-fun mode" (`nofunmode`) that disables the anime-style UI.

### 1.8 Build and Dev Run

```sh
# Install dependencies
cpanm --installdeps tools/cpanfile

# Development server (auto-reload)
LRR_DEVSERVER=1 script/lanraragi daemon

# Production
script/lanraragi daemon -m production
```

The launcher `script/launcher.pl` starts the Mojo web server, then forks Shinobu and Minion worker processes. Logs go to `log/` with automatic rotation (`lib/LANraragi/Utils/RotatingLog.pm`).

### 1.9 Docker Deployment

Official image: `ghcr.io/difegue/lanraragi`. Redis is bundled inside the container (not a sidecar). Content folder and database are mounted as volumes. Environment variables override config:

| Env var | Overrides |
|---------|-----------|
| `LRR_REDIS_ADDRESS` | Redis host:port |
| `LRR_DATA_DIRECTORY` | Content folder |
| `LRR_THUMB_DIRECTORY` | Thumbnail folder |
| `LRR_DISABLE_OPENAPI` | Disable OpenAPI validation |
| `LRR_DEVSERVER` | Debug mode |

Source: `lib/LANraragi/Model/Config.pm` lines 24, 134, 155.

**Relevance to lychee**: Adopt the Docker-first deployment model and env-var override pattern. Avoid bundling Redis — use a proper sidecar or just SQLite. The Redis-as-database approach trades SQL guarantees (ACID, foreign keys, complex queries) for extreme simplicity and fast set operations; lychee's SQLAlchemy/SQLite foundation gives proper relational modeling without the operability headaches of Redis-as-primary-store.

---

## 2. Media Management Model

### 2.1 Archive-Centric Flat Model

LANraragi has **no concept of series, volumes, or libraries** in the data model. Every archive file is a first-class, independent entry. Organization is entirely emergent: by tags, categories, and tankoubons.

### 2.2 Archive ID: SHA-1 of First 512 KB

```perl
# lib/LANraragi/Utils/Database.pm, lines 592-610
sub compute_id ($file) {
    open_path_or_die( my $handle, '<:raw', $file );
    my $data;
    my $len = read $handle, $data, 512000;  # First 512 KB only
    close $handle;

    my $ctx = Digest::SHA->new(1);          # SHA-1
    $ctx->add($data);
    my $digest = $ctx->hexdigest;
    # Guard against null input
    die "..." if $digest eq "da39a3ee5e6b4b0d3255bfef95601890afd80709";
    return $digest;
}
```

The ID is a **40-character lowercase SHA-1 hex string** of only the first 512 KB of the file. This is fast (avoids hashing large archives) but means archives with identical first-512KB blocks will collide (rare in practice for doujinshi). Confirmed: `Digest::SHA->new(1)` = SHA-1, not SHA-256.

### 2.3 Redis Hash Layout for an Archive

```
<sha1_40hex>  (HASH)
  name         =>  "<filename_no_ext>"           # redis_encoded UTF-8
  title        =>  "<display_title>"
  tags         =>  "artist:foo, parody:bar, date_added:1700000000"
  summary      =>  "<optional_description>"
  file         =>  "/abs/path/to/archive.zip"    # raw FS path, not encoded
  isnew        =>  "true" | "false"
  progress     =>  <page_int>                     # current page, 0 = unread
  pagecount    =>  <int>
  lastreadtime =>  <unix_timestamp_int>
  arcsize      =>  <bytes_int>
  toc          =>  '{"0":"Chapter 1","45":"Chapter 2"}'  # optional
  thumbhash    =>  "<sha1_of_cover_image_bytes>"  # for duplicate detection
  thumbjob     =>  <minion_job_id>                # transient
  stamps       =>  '["STAMPS_3_1700000000123", ...]'   # page annotations
```

Source: `lib/LANraragi/Utils/Database.pm` `build_json` (line 234) and `add_archive_to_redis` (line 39).

### 2.4 Categories

Key pattern: `SET_??????????` (14 chars = `SET_` + 10-digit Unix timestamp).

Two modes (distinguished by the `search` field):
- **Static** (`search == ""`): Explicit list of archive IDs stored as a JSON array in the `archives` field. Archives are manually added/removed. Can be linked to a "bookmark" button.
- **Dynamic** (`search != ""`): The `search` field holds a search-engine predicate string (same syntax as the UI search). Archives are not stored; at query time the predicate is parsed and appended to the search tokens.

Source: `lib/LANraragi/Model/Category.pm` lines 95-108, `create_category` line 121.

### 2.5 Tankoubon

Key pattern: `TANK_??????????` (15 chars). Implemented as a Redis ZSET where negative scores encode metadata fields and positive integer scores encode archive membership and reading order.

Tanks appear in search results **in place of** their member archives (controlled by `LRR_TANKGROUPED` set). When a tank is returned, its tags are the union of its own tags plus tags "imputed" from all member archives (deduplicated, with date tags coalesced to the latest value).

A tank's `progress` is a global page number (1-indexed across all archives concatenated in order); `translate_global_page` maps it to a `(archive_id, local_page)` pair.

Source: `lib/LANraragi/Model/Tankoubon.pm` `create_tankoubon` (line 71), `get_tankoubon` (line 126), `get_tank_unified_tags` (line 680).

### 2.6 Multi-Chapter Series

LANraragi offers **no native series/volume hierarchy**. The two workarounds are:

1. **Tankoubon**: Manually group multiple archives in order; read them as one logical unit. Progress tracks across the entire group.
2. **ToC field**: Within a single archive, the `toc` JSON field (`{"<page_0based>": "<chapter_name>"}`) marks chapter boundaries. Exposed in the API as the `toc` array. Used by the reader for chapter navigation within one archive.

There is no automatic series detection from metadata.

**Relevance to lychee**: The absence of a series/volume tree is a deliberate simplicity tradeoff — it works for doujinshi (standalone) but poorly for long-running manga series. Lychee should model a proper `Series → Volume → Chapter` hierarchy in SQLAlchemy while still supporting the "flat archive" entry type for doujinshi. Adopt the Tankoubon concept as "Collection" (manually ordered, cross-format grouping).

---

## 3. File Management and Sync

### 3.1 Content Directory Scanning

At startup, Shinobu runs `update_filemap()` (`lib/Shinobu.pm` line 127):
1. Recursively finds all recognized archive files in `get_userdir()`.
2. Compares against the `LRR_FILEMAP` hash in the config DB (maps path → SHA-1 ID).
3. New files (in FS but not in filemap): processed by `add_new_files()` using `MCE::Loop` parallel workers.
4. Deleted files (in filemap but not on FS): removed from `LRR_FILEMAP`.

File recognition: extension matching via `is_archive()` in `lib/LANraragi/Utils/Generic.pm` line 49:
```perl
/^.+\.(?:zip|rar|7z|tar|tar\.gz|lzma|xz|cbz|cbr|cb7|cbt|cbw|pdf|epub|tar\.zst|zst)$/i
```

### 3.2 Shinobu Event Loop

After initial scan, Shinobu watches the content directory with `File::ChangeNotify` (line 86-92 of `lib/Shinobu.pm`). The filter regex excludes `thumb` and `.` subdirectories. Events: `create`/`modify` → `new_file_callback`; `delete` → `deleted_file_callback`.

On Windows, `File::ChangeNotify` uses polling (no inotify). On Linux, it uses inotify via the kernel. The watcher polls every 1 second (line 106).

### 3.3 Adding a New File

`add_to_filemap()` (line 185):
1. Waits until the file is openable (avoids partial-write race).
2. Waits up to 5 seconds for the file to reach 512 KB (ensures the SHA-1 sample is stable).
3. Calls `compute_id($file)` → 40-char SHA-1.
4. Acquires an exclusive Redis lock `archive-write:<id>` (1 minute timeout, via `exec_with_lock_pure`).
5. Inside the lock: updates `LRR_FILEMAP`, creates the archive hash in DB 0, updates `isnew`, `pagecount`, `arcsize`.
6. Outside the lock: calls `add_new_file()` which runs auto-tagging plugins and generates the cover thumbnail.

### 3.4 ID Uniqueness and Deduplication

If two archives have the same first-512KB content (e.g., a file is re-imported with different metadata), they get the same ID → Redis `RENAME` operation via `change_archive_id()` preserves the existing metadata, updating path and size. Categories and tankoubons referencing the old ID are updated.

Upload endpoint additionally supports `replace_duplicates` config flag: if set, an exact ID match causes the old entry to be deleted before the new one is added.

Source: `lib/Shinobu.pm` `update_filemap_entry` (line 247); `lib/LANraragi/Utils/Database.pm` `change_archive_id` (line 75).

### 3.5 Rename/Move Handling

If Shinobu detects a path discrepancy (file at ID's path doesn't match the stored path), it updates `file` and `name` fields in the archive hash without changing the ID — the SHA-1 stays stable as long as the file content hasn't changed (`lib/Shinobu.pm` `update_filemap_entry` line 295).

### 3.6 Orphan/Missing Handling

`clean_database()` in `lib/LANraragi/Utils/Database.pm` (line 350):
1. Writes an auto-backup JSON before any deletions.
2. Iterates all 40-char Redis keys (archive IDs).
3. For each, checks if the linked file exists. If not, calls `delete_archive()`.
4. If the file exists but the ID is not in `LRR_FILEMAP`, tries to look up the current ID for that path in the filemap. If found, calls `change_archive_id`. Otherwise, unlinks the file reference (sets `file = ""`).

### 3.7 `isnew` Flag

Set to `"true"` when an archive is first added (`add_archive_to_redis` line 68). The API exposes `PUT /api/archives/{id}/isnew` (add new flag) and `DELETE /api/archives/{id}/isnew` (clear). The reader automatically clears it when the archive is opened (`Controller/Api/Archive.pm` `get_file_list` line 301). Stored in `LRR_NEW` set in DB 3.

### 3.8 Minion Queue Role

Minion handles any work that is too slow for a synchronous HTTP response: thumbnail generation, full thumbnail regeneration, full index rebuild (`build_stat_hashes`), URL downloads, plugin batch-runs. Shinobu itself runs outside Minion — it is a long-lived process, not a task queue consumer.

**Relevance to lychee**: The Shinobu + Minion split (filesystem watcher vs. job queue) is a clean pattern. Adopt it: a watchdog/scanner service (Python `watchdog` or `inotify`) for file events, and a task queue (Celery or APScheduler) for heavy async work. The 512KB SHA-1 ID is an interesting compromise; lychee may prefer full-file SHA-256 for correctness at the cost of slightly slower hashing on import, or use a database-assigned UUID to avoid content-hash collision entirely.

---

## 4. Reading Tracker

### 4.1 Per-Archive Progress

The reading state for a single archive is stored directly in the archive hash (DB 0):

| Field | Meaning |
|-------|---------|
| `progress` | Current page number (1-indexed). `0` means unread. |
| `lastreadtime` | Unix timestamp of last progress update. `0` means never read. |
| `isnew` | `"true"` if the archive has never been opened since being added. |

Update endpoint: `PUT /api/archives/{id}/progress/{page}` → sets both `progress` and `lastreadtime` atomically under a write lock; increments `LRR_TOTALPAGESTAT` counter.

Source: `lib/LANraragi/Controller/Api/Archive.pm` `update_progress` (line 422).

### 4.2 "Hide Completed" Filter

Progress > 85% of `pagecount` → archive is considered "completed" and can be filtered out of search results. Uses a Lua script for bulk evaluation (falls back to per-ID round-trips if Lua is unavailable):

```lua
-- lib/LANraragi/Model/Search.pm, hidecompleted block (line 180)
if not (pagecount > 0 and (progress / pagecount) > 0.85) then
    result[#result + 1] = id
end
```

Source: `lib/LANraragi/Model/Search.pm` `search_uncached` (line 172).

### 4.3 Tankoubon Progress

A tankoubon stores a single global page number in its ZSET at score `-3` (`progress_<page>`). The function `translate_global_page` (line 801 of `lib/LANraragi/Model/Tankoubon.pm`) maps a global page to `(archive_id, local_page)` by summing `pagecount` values of archives in order.

### 4.4 Single-Tenant: No Per-User Progress

LANraragi is **not multi-user**. There is one shared progress field per archive. The `enable_localprogress` config flag was intended for a "local browser storage" mode (client-side), while `enable_authprogress` gates the progress API behind API-key auth — but neither mode creates per-user isolation. In practice, all clients see the same progress.

### 4.5 Stamps (Page Annotations)

Stamps are a richer bookmark/annotation system added later. Each stamp is a separate Redis HASH keyed by `STAMPS_<page>_<unix_ms>`. An archive's `stamps` field holds a JSON array of stamp keys. Each stamp has `content` (text), `position` (JSON with coordinates), and `archive_id`.

Source: `lib/LANraragi/Model/Stamp.pm`.

### 4.6 External Sync (Tachiyomi/Mihon)

LANraragi exposes a Tachiyomi/Mihon-compatible extension API through its OpenAPI REST interface. The LANraragi extension for Tachiyomi/Mihon calls the standard `/api/archives` and `/api/archives/{id}/progress/{page}` endpoints. There is no proprietary sync protocol — it's just the same REST API.

**Relevance to lychee**: Adopt per-user progress tracking from day one (SQLAlchemy `UserProgress` table with `user_id`, `archive_id`, `progress_page`, `last_read_at`). The single-user model is a significant limitation for multi-household deployments. The "hide completed" 85% threshold is a useful heuristic worth keeping. The stamp/annotation system is a differentiator worth considering.

---

## 5. Metadata and Tagging

### 5.1 Tag Namespace Model

Tags are stored as a comma-separated string. Each tag is optionally prefixed with a namespace: `namespace:value`. There are no schema-enforced namespaces — any string before `:` is treated as a namespace. Conventional namespaces used throughout the codebase and plugins:

| Namespace | Meaning |
|-----------|---------|
| `artist:` | Creator |
| `group:` | Circle/group |
| `parody:` | Source material |
| `series:` | Serialization |
| `character:` | Character appearing |
| `language:` | `language:english`, etc. |
| `event:` | Convention (Comiket, etc.) |
| `date_added:` | Unix timestamp of import |
| `timestamp:` | Unix timestamp of publication (from plugin) |
| `source:` | Source URL (special: also indexed in `LRR_URLMAP`) |
| `female:`, `male:` | EH-style content tags |
| `read:` | Not a stored tag — a search pseudo-namespace for pages-read filter |
| `pages:` | Not a stored tag — a search pseudo-namespace for page count filter |

Namespaces `artist`, `parody`, `series`, `language`, `event`, `group`, `date_added`, `timestamp`, `source` are classified as "basic" — archives with only these tags are still considered "untagged" in the untagged filter (`lib/LANraragi/Utils/Database.pm` `update_indexes` line 560).

### 5.2 Tag Storage in Redis

Tags are stored as a raw comma-separated string in `<id>.tags`. On every tag update, `update_indexes()` fires (`lib/LANraragi/Utils/Database.pm` line 530):
- Removes the archive ID from all `INDEX_<old_tag>` sets.
- Adds the archive ID to all `INDEX_<new_tag>` sets.
- Adjusts scores in `LRR_STATS`.
- Maintains `LRR_UNTAGGED`.
- For `source:` tags, updates `LRR_URLMAP`.

All tag index keys are lowercased and redis_encoded (UTF-8 NFC bytes).

### 5.3 Tag Rules (Rewriting)

Admin-configurable rules stored as a list (`LRR_TAGRULES` in DB 2) with rule types:

| Rule syntax | Type | Effect |
|-------------|------|--------|
| `-sometag` | `remove` | Delete this tag |
| `-namespace:*` | `remove_ns` | Delete all tags in namespace |
| `~sometag` | `strip_ns` | Remove namespace prefix, keep value |
| `ns1:* -> ns2:*` | `replace_ns` | Rename namespace |
| `old -> new` | (plain) | Rename specific tag |
| `old => {ns: new_map}` | `hash_replace` | Map via lookup table |

Applied by `rewrite_tags()` in `lib/LANraragi/Utils/Tags.pm`, called by the plugin system before committing new tags from any metadata plugin.

### 5.4 Metadata Plugin Architecture

All metadata plugins live in `lib/LANraragi/Plugin/Metadata/`. They are discovered automatically via `Module::Pluggable` and must implement:

```perl
sub plugin_info { return (name=>"...", type=>"metadata", namespace=>"...", ...); }
sub get_tags($lrr_info_href, @params) { return (tags=>"...", title=>"...", summary=>"..."); }
```

The `$lrr_info_href` hash passed to each plugin contains (`lib/LANraragi/Model/Plugins.pm` line 243):
- `archive_id` — Redis ID
- `archive_title` — current title
- `existing_tags` — current tag string
- `thumbnail_hash` — SHA-1 of the cover image (used for reverse image search)
- `file_path` — absolute path to the archive
- `user_agent` — `Mojo::UserAgent` (possibly pre-authenticated by a Login plugin)
- `oneshot_param` — single arbitrary string provided by the user at invocation time

The plugin returns `(tags => "...", title => "...", summary => "...")`. Tags are deduplicated against existing tags before being appended.

**Built-in metadata plugins**: EHentai, Chaika, ChaikaFile (info.json from gallery-dl), Eze (EH downloader JSON), EHDLInfo, nHentai, Hitomi, Pixiv, Fakku, HDoujin, Hentag (SHA-1 image lookup), Koromo, Ksk, MEMS, GalleryDL, ComicInfo (XML inside archives), CopyTags, CopyArchiveTags, DateAdded, RegexParse (filename).

**Login plugins**: EHentai, Fakku, nHentai, Pixiv — return a pre-authed `Mojo::UserAgent` that the matching metadata plugin uses.

**Download plugins**: EHentai, Chaika, Pixiv — given a URL, return either a transformed download URL or a direct file path.

### 5.5 Auto-Plugin on New Files

When Shinobu adds a new file, `exec_enabled_plugins_on_file($id)` is called (`lib/LANraragi/Model/Plugins.pm` line 28). This runs all metadata plugins that the admin has marked as "enabled" in the plugin settings, in order (RegexParse is forced first if enabled). Results are merged with `set_tags($id, $newtags, 1)` (append mode).

### 5.6 Batch Tagging

The Batch Tagging UI (`templates/batch.html.tt2`) enqueues `run_plugin` Minion tasks for each selected archive, optionally filtered by category or "new only". The API endpoint is `POST /api/minion/batchall`.

### 5.7 Search Index Operation

`search_uncached()` in `lib/LANraragi/Model/Search.pm` (line 120) implements the full search:

1. **Base set**: Either all archive IDs (`keys '????????...'`) or `LRR_TANKGROUPED` (if tank-grouping mode).
2. **Category filter**: If static, intersect with the category's archive list. If dynamic, append its predicate tokens.
3. **Untagged / new filters**: Set intersection with `LRR_UNTAGGED` / `LRR_NEW`.
4. **Hide completed**: Lua-script filter on `progress/pagecount > 0.85`.
5. **For each search token**: 
   - Exact match (`isexact`): `SMEMBERS INDEX_<tag>`.
   - Wildcard: `KEYS INDEX_*<tag>*` then `SMEMBERS` each.
   - Title: `ZSCAN LRR_TITLES` with glob `*<token>*`.
   - Negation (`isneg`): array difference instead of intersection.
   - Special pseudo-tags `pages:` and `read:` do per-ID comparisons (not indexed).
6. **Sort**: Title sort uses `ZRANGEBYLEX LRR_TITLES` + natural sort (`nsort`). Other sorts fetch the relevant tag namespace value for each ID via Lua bulk-fetch scripts, then sort in Perl.

The `KEYS` command is used for tag index lookups (an O(N) full-scan of DB 3 keys). This is a known scalability concern for very large collections.

**Relevance to lychee**: The tag namespace model is excellent — adopt it. The flat comma-separated tag string is simple but makes multi-value aggregation queries hard; SQLAlchemy can model tags as a proper M2M table with a namespace column. The search cache strategy (invalidate on any write) is simple but causes cold-start latency on busy collections. Consider a partial invalidation strategy. The `KEYS`-based wildcard tag search does not scale past ~100K archives; lychee should use a proper full-text index (PostgreSQL `tsvector` or SQLite FTS5) instead.

---

## 6. Media Scan and Filename Structure

### 6.1 Archive Discovery

Shinobu's `find_path` call (wrapping `File::Find`) recursively walks the content directory, filtering by `is_archive()`. Symlinks are followed (`follow_symlinks => 1`). Subdirectories are scanned; all archives, regardless of depth, are treated as top-level entries with no hierarchical grouping implied by the folder structure.

The `FolderToCat` script plugin (`lib/LANraragi/Plugin/Scripts/FolderToCat.pm`) is provided as a workaround: it creates a static category per top-level subfolder in the content directory, mirroring folder structure as categories.

### 6.2 Filename Parsing

The `RegexParse` plugin (`lib/LANraragi/Plugin/Metadata/RegexParse.pm`) is the standard filename-to-tag converter. The default regex follows the **doujinshi naming convention**:

```
(Event) [Artist] Title (Series) [Language]
```

Default regex (line 78 of RegexParse.pm):
```
(\((?<event>[^([]+)\))?\s*
(\[(?<artist>[^]]+)\])?\s*
(?<title>[^([]+)\s*
(\((?<series>[^([)]+)\))?\s*
(\[(?<language>[^]]+)\])?
(?<tail>.*)?
```

Named capture groups map directly to tag namespaces. The `artist` group has special handling: `Circle (Artist)` format produces both `group:Circle` and `artist:Artist`. The `tail` group catches everything after the standard fields; optional settings extend capture to all bracketed content, emitting `parsed:` namespace tags for further processing by tag rules.

Underscore-to-space substitution is applied before matching.

### 6.3 Structure Inference

What is inferred automatically:
- Artist, group, series, event, language → from filename (via RegexParse)
- `date_added:` → Unix timestamp of import (configurable: use current time or file modification date)
- `source:` → added automatically when downloading via URL

What is NOT inferred:
- Volume/chapter numbers (no structural parser)
- Publisher / imprint
- Read direction
- Content ratings

### 6.4 "Add to Content Folder" Flow

Upload via `POST /api/archives` (or the upload UI):
1. File is moved to a temp dir.
2. Filename is sanitized (max 255 bytes; 143 if CryptoFS is enabled).
3. `compute_id()` runs.
4. Duplicate check against the ID and against the target filename.
5. File is moved/copied to `get_userdir()` with its original filename.
6. `add_archive_to_redis()` creates the hash; optional `tags`, `title`, `summary` params pre-populate fields.
7. `handle_upload` Minion task wraps the above and is enqueued for URL-downloaded files.

Shinobu's watcher independently picks up the newly moved file and calls its own add path, but `update_filemap_entry` short-circuits if the ID already exists.

Source: `lib/LANraragi/Model/Upload.pm` `handle_incoming_file` (line 41).

**Relevance to lychee**: The doujinshi filename convention parser is immediately useful. Adopt RegexParse's logic as a Python module with the same default regex and named group → namespace mapping. The "no folder-structure hierarchy" is explicitly limiting; lychee should allow both flat import and folder-structure inference (e.g., `Series/Volume/archive.cbz` → series and volume metadata).

---

## 7. Image Decoding and Archives

### 7.1 Supported Container Formats

Recognized extensions (`lib/LANraragi/Utils/Generic.pm` `is_archive`, line 49):
```
.zip .rar .7z .tar .tar.gz .lzma .xz
.cbz .cbr .cb7 .cbt .cbw
.pdf .epub .tar.zst .zst
```

### 7.2 Extraction Library

**Primary**: `Archive::Libarchive` (CPAN wrapper for `libarchive`) — handles ZIP/CBZ, RAR/CBR, 7z/CB7, tar, lzma, xz, zst, EPUB (which is a ZIP), and most other formats. Used in `lib/LANraragi/Utils/Archive.pm`.

Key operations:
- `get_filelist`: `Archive::Libarchive::ArchiveRead` to iterate entries (`next_header` + filter by `is_image`); then natural-sorted.
- `extract_single_file`: `Archive::Libarchive::Peek` to extract one file by path into memory (returns raw bytes, not a temp file).

**PDF**: `libvips` via `FFI::Platypus` (`lib/LANraragi/Utils/Vips.pm`). Pages are rendered as JPEG at 200 DPI (`pdfload_page_dpi`). File list returns synthetic paths `"1.jpg"`, `"2.jpg"`, etc.

**CBW (ComicBookWeb)**: A niche XML format where image data is a list of remote URLs. LRR acts as a proxy: `parse_cbw_xml` parses the XML, `fetch_cbw_image` downloads each page via `Mojo::UserAgent` with browser-like User-Agent. Pages are named `0001.jpg`, `0002.png`, etc. (zero-padded by total count). Downloaded images are stored in `PageCache` to avoid re-fetching. `cbw_prefetch` asynchronously pre-fetches the next 3 pages after each page request.

**Archive::Zip** is also listed in `cpanfile` (line 10) but appears to be a legacy fallback or dependency of another module; the main extraction path is `Archive::Libarchive`.

### 7.3 Image Format Support

Reading images: `is_image()` (`lib/LANraragi/Utils/Generic.pm` line 43) accepts:
```
.png .jpg .gif .bmp .jpeg .jfif .webp .avif .heif .heic .jxl
```

Thumbnail output: JPEG (`.jpg`) by default; JPEG XL (`.jxl`) if `jxlthumbpages` config is enabled.

### 7.4 Page Ordering

After listing all image entries from an archive, `get_filelist` applies:

1. **Natural sort**: The `expand()` sub (line 309 of `lib/LANraragi/Utils/Archive.pm`) zero-pads all digit sequences to 4 chars before comparison, producing `0001.jpg < 0002.jpg < 0010.jpg`. Uses `Sort::Naturally::nsort`.
2. **Cover reordering**: Pages matching `^(?!.*(back|end|rear|recover|discover)).*cover.*/i` are moved to the front.
3. **Credit/misc reordering**: Pages matching patterns for translator credits, artist info, notes, `999*` are moved to the end.

Apple fork/signature files (`__MACOSX/`, `._*` prefixes, AppleSingle/AppleDouble magic bytes) are filtered out.

### 7.5 Thumbnail Generation and Caching

Thumbnails are generated by `extract_thumbnail()` (`lib/LANraragi/Utils/Archive.pm` line 247).

**Storage layout**:
```
<thumbdir>/
  <id[0:2]>/           # 2-char subfolder for FS optimization
    <id>.jpg           # cover thumbnail (main)
    <id>.jxl           # (if JXL mode)
    <id>/
      1.jpg            # per-page thumbnails
      2.jpg
      ...
  TA/                  # tank thumbnails
    <tank_id>.jpg
```

**Thumbnail generation pipeline**:
1. `get_filelist()` on the archive → get first image path.
2. `extract_single_file()` → raw image bytes.
3. `generate_thumbnail()` → calls `get_resizer()`:
   - **libvips preferred** (`LANraragi::Utils::VipsResizer`): FFI bindings to `libvips`. Resize to height 500 px, quality 50 (default) or 80 (HQ mode).
   - **ImageMagick fallback** (`LANraragi::Utils::ImageMagickResizer`): `Image::Magick` (or `Imager` — not a CPAN dependency in `cpanfile`, suggesting `Image::Magick` must be system-installed).
4. Write to `$thumbname`.

For cover thumbnails, the SHA-1 hash of the raw image bytes is stored as `thumbhash` (used by the `find_duplicates` task to compare covers via Hamming distance on the hex string).

Non-cover (per-page) thumbnails are generated on demand when the reader requests them or when the `generate_page_thumbnails` API is called. They are queued as low-priority Minion jobs.

### 7.6 On-the-Fly Resizing

If `enable_resize` is set in config, `serve_page()` resizes images before serving. The threshold is `sizethreshold` kB; quality is `readerquality`. The resizer's `resize_page()` method converts to JPEG. Results are cached in `PageCache` (CHI FastMmap on disk, max configurable MB, default 500 MB). Cache key: `"resize_page/<id>/<path>/<threshold>/<quality>"`.

Source: `lib/LANraragi/Model/Archive.pm` `serve_page` (line 260).

### 7.7 Large / Corrupt / Encrypted Archives

- **Corrupt/unreadable**: `Archive::Libarchive` returns an error code; `get_filelist` dies with a detailed message including file existence, readability, and libarchive error string. The exception is caught in Shinobu (`add_new_files` eval block) and logged; the archive is skipped.
- **Encrypted archives**: libarchive will fail to read protected entries; behavior depends on the archive format. There is no UI for entering passwords.
- **Large archives**: No special handling — all file-list iteration is streaming (entries are read one at a time). Single-file extraction (`Peek`) loads one file into memory; for very large single images this could be a concern.
- **Unsupported format**: Upload rejected with HTTP 415.

**Relevance to lychee**: The libarchive approach via `Archive::Libarchive` should map cleanly to Python's `libarchive-c` or the `patool`/`rarfile`/`zipfile` stack. PDF rendering via libvips (a well-maintained C library with Python bindings via `pyvips`) is a good choice to replicate. The natural sort + cover/credit reordering heuristic is worth porting. The two-tier thumbnail cache (cover in `<thumbdir>/<prefix>/<id>.jpg`, per-page in `<thumbdir>/<prefix>/<id>/<page>.jpg`) is a clean filesystem layout to adopt. Consider adopting CHI-equivalent (Python `diskcache` or a Redis-backed cache) for the page image cache.

---

## Notable Design Decisions, Tradeoffs, and Pain Points

### Redis-Only Persistence

**Pro**: Zero SQL migration headaches; extremely fast set operations for tag indexes; trivial backup (BGSAVE or export to JSON).

**Con**: No referential integrity (dangling category references after archive deletion must be manually cleaned up — see `delete_archive` in `lib/LANraragi/Model/Archive.pm` line 382). No complex aggregation queries without Lua scripts. Redis restart without persistence = data loss. `KEYS` command for ID enumeration is O(N) — will block at scale.

### SHA-1 Content Hash as Primary Key

**Pro**: Deduplication across renamed files; stable ID after rename/move; no auto-increment awkwardness.

**Con**: Only 512KB sample → files that share a header/cover but have different content get the same ID. SHA-1 is cryptographically weak (collision attacks exist) though collision risk in practice for self-hosted use is negligible. Change detection (Shinobu) relies on the hash changing when content changes, which won't happen if only the latter part of the file changes.

### No Series Hierarchy

**Pro**: Simplicity; works great for self-contained doujinshi.

**Con**: Multi-volume manga must be grouped manually via Tankoubon or tags. Tankoubon progress tracking is a workaround for what should be a first-class reading continuation feature.

### Plugin System Scalability

Plugin discovery at startup via `Module::Pluggable` scans the `@INC` directories — fast and automatic but requires Perl module namespace conventions. Adding third-party plugins means dropping a `.pm` file into the right package path.

The auto-plugin runs synchronously in Shinobu's add-file path (after thumbnail generation), which can block the watcher's event loop if a plugin is slow (e.g., rate-limited by E-Hentai). A `cooldown` field exists in plugin metadata but is not enforced by the current batch execution code.

### Search Cache Invalidation

Any metadata change (including reading progress updates, which call `invalidate_cache()` indirectly via `set_isnew`) nukes the entire `LRR_SEARCHCACHE` hash. For active multi-user deployments this would cause constant cache misses. For single-user use it is acceptable.

### Unicode Handling

The "double-decode" hack in `redis_decode()` (`lib/LANraragi/Utils/Redis.pm` line 27) is a historical artifact: early versions double-encoded UTF-8 when writing to Redis. The eval-guarded double-decode handles both old (double-encoded) and new (single-encoded) data transparently.

### CBW Format (Comic Book Web)

A niche format from mobileread.com that stores comic pages as remote URLs (CDN links). LRR proxies these through the server, which means the server needs internet access to serve pages from CBW archives. This is the only format where the server is not self-contained.

---

## Relevance to Lychee — Summary per Section

| Section | Adopt | Avoid / Adapt |
|---------|-------|---------------|
| Stack | Plugin architecture concept; Minion-style async job queue; separate file-watcher process | Redis-as-only-database; single shared user model |
| Media model | Content-hash ID (consider full SHA-256); tag namespace system; category (static/dynamic) duality; Tankoubon → "Collection" concept | Flat tag string in one field (use relational M2M); absence of series hierarchy |
| File sync | Watcher + filemap pattern; write-lock per archive during scan; "isnew" flag on first import | 512KB-only hash (use full-file hash or UUID); `KEYS`-based enumeration |
| Reading tracker | Per-archive progress + lastreadtime; "hide completed" 85% heuristic; stamps/annotations concept | Single shared progress (add per-user); no granular sync protocol (add Tachiyomi-compatible API natively) |
| Metadata/tagging | Tag namespace model; tag rewrite rules; plugin-based auto-tagging; "source:" URL dedup | Comma-string tag storage; `KEYS`-based wildcard tag search (use SQL FTS or proper index); no enforced tag vocabulary |
| Scan/filename | RegexParse doujinshi regex; "add to content folder" upload flow; auto-detect archive type by extension | No folder-structure hierarchy inference; no volume/chapter number parsing |
| Image decoding | libarchive for archive extraction; libvips for PDF + thumbnails; natural sort + cover/credit reordering; 2-level thumbnail directory layout | In-memory single-file extraction for large files; no encrypted archive support; no progressive JPEG or WebP output (add for bandwidth) |
