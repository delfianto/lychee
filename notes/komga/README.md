# Komga Deep-Dive Analysis

> Reference implementation study for the **lychee** media server project.
> All claims are backed by source file references. Inferences are marked **[inference]**.

---

## Quick Facts

| Property | Value |
|---|---|
| **Version analyzed** | 1.25.0 (from `gradle.properties`) |
| **Stack** | Kotlin 2.2.0 + Spring Boot 3.5.14, Vue 2.6 + Vuetify 2 + TypeScript frontend |
| **JVM target** | Java 17 (compile), Java 21+ required to run |
| **Database** | SQLite via `sqlite-jdbc 3.50.2.0`; jOOQ 3.19.32 as query DSL; Flyway 11.7.2 for migrations |
| **Search** | Apache Lucene 9.9.1 in a separate FSDirectory on disk |
| **Media hierarchy** | Library → Series → Book → Media (pages + files) |
| **Standout features** | KOReader sync, native Kobo device sync (KEPUB), page-level dedup hashing, one-shot virtual series, full OPDS v1 + v2, WebPub Manifest (Divina/EPUB/PDF profiles), content restrictions |
| **Default port** | 25600 |
| **Config root** | `~/.komga/` (database.sqlite, tasks.sqlite, lucene/, logs/) |

---

## TL;DR

Komga is a well-layered Spring Boot application that persists everything in SQLite and offloads full-text search to a local Lucene directory. The domain model has a hard Library → Series → Book chain with an "one-shot" escape hatch (a book that generates its own virtual series). Book and page ordering rely entirely on natural sort of filenames; metadata providers (ComicInfo.xml, EPUB OPF, Mylar series.json) can override display labels and sort keys via per-field lock flags. All long-running work goes through a SQLite-backed task queue processed by a configurable thread pool. Read progress is stored per-book-per-user with an R2Locator blob for fine-grained EPUB position. Kobo and KOReader devices sync over dedicated protocol endpoints. Thumbnails are stored as BLOBs in the database (or as sidecar URL references). There is no inotify/file-watching; consistency is maintained purely through periodic scheduled scans plus manual triggers.

---

## 1. Stack

### Languages and Frameworks

- **Backend**: Kotlin 2.2.0, Spring Boot 3.5.14 (`komga/` subproject)
- **Frontend**: Vue 2.6 + Vuetify 2 + TypeScript (`komga-webui/`), bundled at compile time and served as static assets by the Spring backend via Thymeleaf templates
- **Desktop wrapper**: `komga-tray/` — thin tray-icon companion, not part of the server itself
- **Build**: Gradle 8.14.3 with Kotlin DSL; `./gradlew bootRun` for local dev; frontend built via `./gradlew prepareThymeLeaf` → npm

### Database

- **Engine**: SQLite via `org.xerial:sqlite-jdbc 3.50.2.0`
- **Query DSL**: jOOQ 3.19.32. Schema is generated from actual SQLite databases produced by Flyway migrations at build time; generated classes live under `org.gotson.komga.jooq.main` and `org.gotson.komga.jooq.tasks` (see `komga/build.gradle.kts` lines 311-358).
- **Migrations**: Flyway 11.7.2 with both `.sql` files and Kotlin `.kt` migration classes; located in `komga/src/flyway/resources/db/migration/sqlite/` and `komga/src/flyway/kotlin/db/migration/sqlite/`.
- **Two databases**:
  - `~/.komga/database.sqlite` — main domain data
  - `~/.komga/tasks.sqlite` — task queue (separate SQLite file for isolation)

### Key Libraries (`komga/build.gradle.kts`)

| Purpose | Library | Version |
|---|---|---|
| HTTP API | Spring Boot Starter Web + WebFlux | 3.5.14 |
| Security | Spring Security, Spring OAuth2 Client | via Boot BOM |
| Session | spring-session-caffeine (in-memory, Caffeine-backed) | 2.1.0 |
| Lucene FTS | lucene-core, lucene-analysis-common, lucene-queryparser, lucene-backward-codecs | 9.9.1 |
| Hashing | appmattus/cryptohash (XXH3-128 + MD5 for KOReader) | 1.0.2 |
| Archive: ZIP | Apache Commons Compress (ZipFile) | 1.27.1 |
| Archive: RAR4 | junrar | 7.6.0 |
| Archive: RAR5 | nightcompress (native JNI wrapper) | 1.1.1 |
| PDF | Apache PDFBox | 3.0.5 |
| HTML parsing (EPUB) | Jsoup | 1.21.1 |
| Content detection | Apache Tika | 2.9.1 |
| Thumbnail resizing | thumbnailator | 0.4.20 |
| ImageIO: JPEG/TIFF/WebP | TwelveMonkeys imageio | 3.12.0 |
| ImageIO: JXL | nightmonkeys/imageio-jxl | 1.0.0 |
| ImageIO: HEIF/AVIF | nightmonkeys/imageio-heif | 1.0.0 |
| ImageIO: JPEG2000 | jai-imageio-jpeg2000 | 1.4.0 |
| ImageIO: JBIG2 | pdfbox/jbig2-imageio | 3.0.4 |
| ISBN barcode | Google ZXing core | 3.5.3 |
| ICU i18n sort | icu4j | 77.1 |
| Natural sort | natural-comparator | 1.1 |
| ID generation | tsid-creator (TSID-256) | 5.2.6 |
| API docs | springdoc-openapi | 2.8.9 |
| XML (ComicInfo) | jackson-dataformat-xml | via Boot BOM |

### Background Jobs and Scheduling

- **Task queue**: persisted in `tasks.sqlite` (`TASK` table; `komga/src/flyway/resources/tasks/migration/sqlite/V20231013114850__tasks.sql`). Each task has a priority (0=LOWEST, 8=HIGHEST), optional `GROUP_ID` (to serialize tasks for the same series), `CLASS`, `SIMPLE_TYPE`, `PAYLOAD` (JSON).
- **Task processor**: `TaskProcessor.kt` — Spring `ApplicationEventPublisher` event `TaskAddedEvent` triggers `processAvailableTask()`. A `ThreadPoolTaskExecutor` (configurable pool size, default 1) calls `tasksRepository.takeFirst()` → `taskHandler.handleTask()`. After a task completes it immediately tries to pick up the next.
- **Library scan scheduler**: `LibraryScanScheduler.kt` — each library can have its own `ScanInterval` (DISABLED, HOURLY, EVERY_6H, EVERY_12H, DAILY, WEEKLY). Spring `ScheduledTaskRegistrar` with fixed-rate tasks per library.
- **On-startup scan**: `PeriodicScannerController.kt` — if `library.scanOnStartup == true`, emits a `ScanLibrary` task immediately on `ApplicationReadyEvent`.
- **Domain events**: `DomainEvent` sealed class hierarchy published via `ApplicationEventPublisher`. SSE controller listens and forwards to connected clients (`/sse/v1/events`).

### API Styles

| Style | Path prefix | Notes |
|---|---|---|
| REST JSON | `/api/v1/` | Main API for web UI and integrations |
| OPDS 1.2 | `/opds/v1.2/` | Atom XML (standard catalog) |
| OPDS 2.0 | `/opds/v2/` | JSON (experimental) |
| WebPub Manifest | `/api/v1/books/{id}/manifest` | Divina / EPUB / PDF profiles |
| KOReader Sync | `/koreader/` | Custom progress sync for KOReader devices |
| Kobo Sync | `/kobo/{authToken}/` | Kobo device library sync protocol |
| SSE | `/sse/v1/events` | Server-Sent Events for live UI updates |
| Actuator | via Spring Boot Actuator | Health, metrics, scheduled tasks info |

### Authentication

Configured in `SecurityConfiguration.kt`:
- **Session-based** (cookie): Spring Security form login; session stored in Caffeine-backed spring-session (in-memory, not DB); session timeout 7 days.
- **HTTP Basic**: enabled (used by OPDS clients, etc.)
- **API Keys**: `USER_API_KEY` table; custom `ApiKeyAuthenticationFilter` extracts key from `X-API-Key` header or URI regex; hashed with XXH3-128 before storage.
- **OAuth2 / OIDC**: supported via Spring OAuth2 Client (`oauth2Enabled` flag based on whether `InMemoryClientRegistrationRepository` is present)
- **Remember-Me**: `TokenBasedRememberMeServices` with key stored in `SERVER_SETTINGS` table (random 32-byte hex)
- **Roles**: `ADMIN`, `FILE_DOWNLOAD`, `PAGE_STREAMING`, `KOBO_SYNC`, `KOREADER_SYNC` stored in `USER_ROLE` table (many-to-many; migrated from boolean columns in `V20250108115503__user_roles.sql`).

### Search (Lucene)

- Lucene 9.9.1 index lives in `~/.komga/lucene/` (`FSDirectory` with `SingleInstanceLockFactory`).
- **Indexing analyzer**: `MultiLingualNGramAnalyzer` (n-gram, preserves original token; configurable min/max gram).
- **Query analyzer**: `MultiLingualAnalyzer`.
- **Indexed entities**: `LuceneEntity` enum — Book, Series, Collection, ReadList (`LuceneEntity.kt`).
- Indexed fields per entity defined in `LuceneEntity.kt`; books index title, isbn, tags, authors, release_date, status, deleted, oneshot; series additionally indexes publisher, reading_direction, age_rating, language, genres, sharing_labels, complete.
- **History**: SQLite FTS5 tables were added in `V20210727102041__full_text_search.sql` then **dropped** in `V20210805174355__remove_full_text_search.sql` and replaced by Lucene.

### Build and Dev Run

```sh
# Backend with in-memory DB, auto user creation:
./gradlew bootRun --args='--spring.profiles.active=dev,noclaim'

# Backend with persistent local DB:
./gradlew bootRun --args='--spring.profiles.active=dev,localdb,noclaim'

# Frontend dev server (hot reload against localhost:25600):
cd komga-webui && npm run serve

# Generate jOOQ DSL after schema changes:
./gradlew generateJooq

# Run tests:
./gradlew test
```

Spring profiles of note: `dev` (more logging, CORS for localhost:8081, in-memory DB), `localdb` (stores DB at `./localdb`), `noclaim` (creates initial users).

**Relevance to lychee**: Python/FastAPI has no Spring-style auto-wiring, but the overall pattern — SQLAlchemy as ORM, Alembic for migrations, APScheduler or Celery for tasks — maps cleanly. The two-database split (main + tasks) is worth considering; lychee could use a single SQLite with a tasks table or a Redis-backed queue. SSE is easy in FastAPI (StreamingResponse or `sse-starlette`). Replace Lucene with SQLite FTS5 (built into SQLite) or a lightweight Python wrapper around Tantivy.

---

## 2. Media Management Model

### Entity Hierarchy

```
Library  1──────*  Series  1──────*  Book  1──────1  Media
                                               ├──── BookPage[]
                                               ├──── MediaFile[]
                                               └──── MediaExtension (EPUB blob)

Library  *──────*  Collection  *──────*  Series  (COLLECTION_SERIES join)
                   ReadList    *──────*  Book     (READLIST_BOOK join)

Series  1──────1  SeriesMetadata
Book    1──────1  BookMetadata
Series  1──────1  BookMetadataAggregation  (aggregated from child books)
```

### Core Domain Models

**Library** (`Library.kt`, `LIBRARY` table — `V20200706141854__initial_migration.sql`):
- `id` (TSID-256 string), `name`, `root` (URL path), `createdDate`, `lastModifiedDate`
- Per-library feature flags: `importComicInfoBook`, `importComicInfoSeries`, `importComicInfoCollection`, `importComicInfoReadList`, `importComicInfoSeriesAppendVolume`, `importEpubBook`, `importEpubSeries`, `importMylarSeries`, `importLocalArtwork`, `importBarcodeIsbn`
- Scan settings: `scanOnStartup`, `scanInterval` (DISABLED/HOURLY/EVERY_6H/EVERY_12H/DAILY/WEEKLY), `scanCbx`, `scanPdf`, `scanEpub`, `scanDirectoryExclusions`, `scanForceModifiedTime`
- Maintenance: `repairExtensions`, `convertToCbz`, `emptyTrashAfterScan`, `seriesCover` (FIRST/FIRST_UNREAD_OR_FIRST/FIRST_UNREAD_OR_LAST/LAST)
- Hashing: `hashFiles`, `hashPages`, `hashKoreader`
- Other: `analyzeDimensions`, `oneshotsDirectory`, `unavailableDate`

**Series** (`Series.kt`, `SERIES` table):
- `id`, `name` (directory name), `url` (directory path as URL), `fileLastModified`, `libraryId`, `bookCount` (denormalized), `deletedDate` (soft delete), `oneshot` (boolean flag)

**Book** (`Book.kt`, `BOOK` table):
- `id`, `name` (filename without extension), `url` (file path as URL), `fileLastModified`, `fileSize`, `fileHash` (XXH3-128), `fileHashKoreader` (partial MD5, KOReader-compatible), `number` (Int, 1-based position in series, for sort order), `seriesId`, `libraryId`, `deletedDate`, `oneshot`

**Media** (`Media.kt`, `MEDIA` table):
- `bookId` (PK = book FK), `status` (UNKNOWN/ERROR/READY/UNSUPPORTED/OUTDATED), `mediaType` (MIME string), `pageCount`, `comment` (error code string, e.g. "ERR_1006"), `epubDivinaCompatible`, `epubIsKepub`
- Extended fields added via migration: `EXTENSION_CLASS`, `EXTENSION_VALUE` — stores `MediaExtensionEpub` as a JSON blob for EPUB TOC/landmarks/positions.

**BookPage** (`BookPage.kt`, `MEDIA_PAGE` table):
- `(BOOK_ID, NUMBER)` composite PK; `FILE_NAME`, `MEDIA_TYPE`, `NUMBER` (1-based), `WIDTH`, `HEIGHT` (added migration), `FILE_SIZE`, `FILE_HASH` (page-level XXH3-128, optionally computed)

**MediaFile** (`MediaFile.kt`, `MEDIA_FILE` table):
- Non-image entries in an archive (e.g. ComicInfo.xml, fonts in EPUB); `FILE_NAME`, `MEDIA_TYPE`, `SUB_TYPE`, `FILE_SIZE`, `BOOK_ID`

**BookMetadata** (`BookMetadata.kt`, `BOOK_METADATA` table):
- `title`, `summary`, `number` (String display label, e.g. "1.5"), `numberSort` (Float sort key), `releaseDate`, `isbn`, `publisher`, `readingDirection`, `ageRating`
- Every field has a corresponding `*Lock` boolean (`NUMBER_LOCK`, `NUMBER_SORT_LOCK`, etc.)
- Related tables: `BOOK_METADATA_AUTHOR` (name, role, book_id), `BOOK_METADATA_TAG` (tag, book_id), `BOOK_METADATA_LINK` (label, url, book_id)

**SeriesMetadata** (`SeriesMetadata.kt`, `SERIES_METADATA` table):
- `title`, `titleSort`, `summary`, `status` (ENDED/ONGOING/ABANDONED/HIATUS), `readingDirection` (LEFT_TO_RIGHT/RIGHT_TO_LEFT/VERTICAL/WEBTOON), `publisher`, `ageRating`, `language` (BCP-47), `totalBookCount`
- Related tables: `SERIES_METADATA_GENRE`, `SERIES_METADATA_TAG`, `SERIES_METADATA_SHARING_LABEL`, `SERIES_METADATA_LINK`, `SERIES_METADATA_ALTERNATE_TITLE`
- Every field has a `*Lock` boolean

**BookMetadataAggregation** (`BOOK_METADATA_AGGREGATION` table, `V20210111113543`):
- Aggregated per-series metadata computed from all books: `RELEASE_DATE`, `SUMMARY`, `SUMMARY_NUMBER`
- Related: `BOOK_METADATA_AGGREGATION_AUTHOR`, `BOOK_METADATA_AGGREGATION_TAG`

### One-Shots

A one-shot is a standalone book (manga volume, graphic novel) that does not belong to an ongoing series. Modeled in two ways:
1. **Virtual one-shot series**: if a book file sits inside the configured `oneshotsDirectory` path string, `FileSystemScanner.scanRootFolder()` creates a synthetic `Series` object with `oneshot=true` and the series URL pointing at the book file itself (not the directory). See `FileSystemScanner.kt` lines 159–168.
2. Both `Series.oneshot` and `Book.oneshot` are set to `true`.
3. `OneShotSeriesProvider.kt` copies the book's title/summary into the series metadata.

### Collections and Read Lists

- **Collection** (`COLLECTION`, `COLLECTION_SERIES`): groups of Series; optionally ordered (`ORDERED` boolean). The `NUMBER` column in `COLLECTION_SERIES` tracks ordering position.
- **ReadList** (`READLIST`, `READLIST_BOOK`): cross-series ordered book lists (e.g. a reading order for a crossover event). The `NUMBER` column tracks position.

### Number / Chapter Representation

- `BOOK_METADATA.NUMBER` (varchar): human-readable display label (e.g. "1", "1.5", "0.5 SP")
- `BOOK_METADATA.NUMBER_SORT` (real/float): numeric sort key; derived from `Number.toFloatOrNull()` in `ComicInfoProvider.kt` (line 113)
- `BOOK.NUMBER` (integer): 1-based ordinal within the series; set by `SeriesLifecycle.sortBooks()` using natural sort on filename (`SeriesLifecycle.kt` lines 67–119)
- When `NUMBER_LOCK=false` and `NUMBER_SORT_LOCK=false`, both display and sort numbers are reset to the file's position index on each scan. When a lock is set, the metadata provider's value is preserved.

### IDs

All entity IDs are TSID-256 strings (time-sortable, collision-resistant) generated via `com.github.f4b6a3:tsid-creator 5.2.6`. This gives natural time-ordering for free.

**Relevance to lychee**: The hierarchy maps directly to Python dataclasses or SQLAlchemy ORM models. The `numberSort` (float) pattern for chapter ordering is robust — adopt it. The lock-flag pattern (one bool per metadata field) is verbose but unambiguous — consider a single `locked_fields: list[str]` JSON column instead. TSID is language-agnostic; Python has `uuid-utils` or `python-tsid` for equivalent.

---

## 3. File Management and Sync

### Scan Pipeline

`LibraryContentLifecycle.scanRootFolder()` (`LibraryContentLifecycle.kt`) orchestrates:

1. **Walk the filesystem**: delegates to `FileSystemScanner.scanRootFolder()` which calls `Files.walkFileTree()` with `FileVisitOption.FOLLOW_LINKS` and `Integer.MAX_VALUE` depth.
2. **Directory → Series**: every visited directory becomes a tentative `Series` (name = dir name, url = dir path, `fileLastModified = max(creationTime, lastModifiedTime)` via `BasicFileAttributes.getUpdatedTime()`).
3. **File → Book**: files matching scanned extensions (`cbz`, `zip`, `cbr`, `rar`, `pdf`, `epub` by default; configurable per library) and not starting with `.` become `Book` objects.
4. **One-shot override** (`postVisitDirectory`): if the directory's path contains the configured `oneshotsDirectory` string, each book gets its own virtual series (`Series(name=book.name, url=book.url, oneshot=true)`).
5. **Hidden dirs**: skipped if name starts with `.` or matches any `directoryExclusions` string.

**Back in `LibraryContentLifecycle`**:
6. **Soft-delete missing series**: series in DB but not on disk → `seriesLifecycle.softDeleteMany()` (sets `deletedDate`).
7. **Soft-delete missing books**: same pattern.
8. **For each scanned series**: compare `fileLastModified` to stored value. If changed (or `scanDeep=true`):
   - Match books by URL. If a book's `fileLastModified` changed:
     - If `fileSize` is the same and DB has a hash: re-hash the file. If hash matches → update timestamps only, no media re-analysis. If hash differs → set `Media.status = OUTDATED`.
   - Add new books (not matched by URL).
9. **Sort + refresh metadata**: for any series with changed book list.
10. **Sidecars**: compare `lastModifiedTime`; if new or changed, emit `refreshSeriesMetadata` or `refreshSeriesLocalArtwork` task.
11. **Trash**: if `emptyTrashAfterScan=true`, permanently delete soft-deleted items.

### Move/Rename Detection (Restore)

`tryRestoreBooks()` and `tryRestoreSeries()` in `LibraryContentLifecycle.kt` attempt to match newly added items to soft-deleted ones:
- Match by `fileSize`, then confirm with `fileHash` (computes hash if needed)
- On match: copy `Media`, thumbnails, `BookMetadata`, `ReadProgress`, `ReadList` membership from the deleted record to the new one, then hard-delete the old record.
- Series restore also copies `SeriesMetadata` (respecting title lock), user-uploaded thumbnails, and collection memberships.

### Hashing

- **File hash** (`Hasher.kt`): XXH3-128 seeded at 0, applied to full file byte stream via `Algorithm.XXH3_128.Seeded(0L).createDigest()` from `com.appmattus.crypto:cryptohash 1.0.2`. Result is hex string. Stored in `BOOK.FILE_HASH`.
- **KOReader hash** (`KoreaderHasher.kt`): partial MD5 — reads 1 KB chunks at exponential offsets (`step shl (2 * it)` for `it` in -1..10), as specified by [KOReader's Lua implementation](https://github.com/koreader/koreader/blob/5bd3f3b42c95fd143d98f8fc9695d486fd92b7c8/frontend/util.lua#L1093-L1119). Stored in `BOOK.FILE_HASH_KOREADER`.
- **Page hash** (`BookAnalyzer.hashPages()`): XXH3-128 of page content bytes; for JPEG, the image is decoded and re-encoded first (to strip varying EXIF metadata). Only first and last N pages are hashed (configurable `komgaProperties.pageHashing`, default likely 3). Stored in `MEDIA_PAGE.FILE_HASH`.
- **Page hash dedup** (`PAGE_HASH` table, `V20220128152310`): stores known hashes with an `ACTION` (delete/ignore) and `DELETE_COUNT`. Used to find duplicate pages (e.g. ad pages) across books and optionally delete them. Migrated from MD5 to XXH3-128 in `V20230626150454__xxhash128.sql`.

### Change Detection

- Primary signal: `max(creationTime, lastModifiedTime)` of the directory (for series) or file (for book), stored as `FILE_LAST_MODIFIED`.
- Secondary: file size + hash for verifying that a mtime change was a real content change.
- **No inotify/file watching**: Komga does not use `WatchService` or any filesystem notification mechanism. Everything is polling-based.

### Scan Locking

No explicit file-level locks. The task queue serializes work via group IDs (tasks for the same series share a `GROUP_ID` and are processed sequentially within a group). Spring's `@Transactional` / `transactionTemplate.executeWithoutResult {}` wraps DB writes.

**Relevance to lychee**: The two-phase scan (walk filesystem, then reconcile with DB) is the right approach for any media server. The partial hash for KOReader is a clever compatibility trick — implement it exactly if KOReader support is wanted. XXH3-128 is fast and available in Python via `xxhash` package. File watching with `watchfiles` or `inotify-simple` would be a useful addition that Komga lacks.

---

## 4. Reading Tracker

### ReadProgress Model

`READ_PROGRESS` table (initial migration + additions via `V20210914111439`, `V20231206152158`):

```sql
CREATE TABLE READ_PROGRESS (
    BOOK_ID            varchar  NOT NULL,
    USER_ID            varchar  NOT NULL,
    CREATED_DATE       datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
    LAST_MODIFIED_DATE datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PAGE               int      NOT NULL,        -- last read page (1-based)
    COMPLETED          boolean  NOT NULL,         -- explicit completion flag
    READ_DATE          datetime,                  -- when completion was recorded
    device_id          varchar  DEFAULT '',       -- device identifier
    device_name        varchar  DEFAULT '',       -- human-readable device name
    locator            blob,                      -- JSON: R2Locator (Readium)
    PRIMARY KEY (BOOK_ID, USER_ID)
);
```

`ReadProgress.kt`: `bookId`, `userId`, `page`, `completed`, `readDate`, `deviceId`, `deviceName`, `locator: R2Locator?`

**R2Locator** (`R2Locator.kt`): Readium Web Publication position object with `href`, `type`, and `locations` (containing `position`, `progression` 0..1, `totalProgression` 0..1).

**Series-level aggregation** (`READ_PROGRESS_SERIES` table, `V20210526113555`):
```sql
CREATE TABLE READ_PROGRESS_SERIES (
    SERIES_ID         varchar NOT NULL,
    USER_ID           varchar NOT NULL,
    READ_COUNT        int     NOT NULL,   -- # of completed books
    IN_PROGRESS_COUNT int     NOT NULL,   -- # of started but not completed books
    PRIMARY KEY (SERIES_ID, USER_ID)
);
```
Also updated via `V20240906152500__read_progress_series_read_date.sql` to track `READ_DATE`.

### Multi-User

- Every `READ_PROGRESS` row is scoped to `(BOOK_ID, USER_ID)` — fully per-user.
- Library access control: `USER_LIBRARY_SHARING` + `USER.SHARED_ALL_LIBRARIES`; content restrictions via `USER.AGE_RESTRICTION`, `USER_CONTENT_RESTRICTION` (labels allow/exclude).

### KOReader Sync (`/koreader/`)

Controller: `KoreaderSyncController.kt`

- Implements the [KOReader Progress Sync](https://github.com/koreader/koreader-sync-server) protocol.
- **Authentication**: books are identified by KOReader hash (`BOOK.FILE_HASH_KOREADER`), not by Komga ID. The hash must be computed and stored first (opt-in per library: `library.hashKoreader`).
- `GET /koreader/users/auth` — returns mock auth (user creation always returns 403)
- `GET /koreader/syncs/progress/{bookHash}` — returns progress as `DocumentProgressDto` (document hash, percentage, progress string, device)
- `PUT /koreader/syncs/progress` — updates progress

Progress format translation (`KoreaderSyncController.kt` lines 79–203):
- **DIVINA/PDF**: `progress` field is the page number as string; `percentage` = `page / pageCount`
- **EPUB**: KOReader uses `DocFragment[N].0` or `#_doc_fragment_N_` strings; Komga maps these to an EPUB spine resource index, then to an `R2Locator` with `href` of that resource.

Role required: `KOREADER_SYNC` (in `USER_ROLE`).

### Kobo Sync (`/kobo/{authToken}/`)

Controller: `KoboController.kt`; infrastructure in `komga/src/main/kotlin/org/gotson/komga/infrastructure/kobo/`

- Implements the Kobo library sync protocol so a physical Kobo device can use Komga as its book store.
- Uses a **SyncPoint** mechanism: `SYNC_POINT` table records a snapshot of the library state for each sync session, tracking which books have been synced (`SYNC_POINT_BOOK`) and which were removed (`SYNC_POINT_BOOK_REMOVED_SYNCED`). See `V20240529120934__syncpoint.sql`.
- Supports KEPUB (`Media.epubIsKepub`); `KepubConverter.kt` converts standard EPUB to KEPUB format for Kobo-native rendering.
- `KoboProxy.kt` can optionally proxy requests to the real Kobo store (pass-through for store purchases).
- Role required: `KOBO_SYNC`.

### OPDS

- **OPDS 1.2** (`/opds/v1.2/`): Atom XML; standard acquisition feeds for series, books, libraries, collections, read lists; supports search.
- **OPDS 2.0** (`/opds/v2/`): JSON; same catalog structure but JSON-based.
- Both support Basic Auth.

**Relevance to lychee**: The `ReadProgress` schema is clean — adopt it. The `locator` blob (R2Locator JSON) is the right abstraction for EPUB progress. For DIVINA/CBZ, storing `page` (integer) is sufficient. Consider adding `locator` as a nullable JSON column from day one to avoid a migration later. KOReader sync is highly desirable — the partial MD5 hash and the progress string parsing are the hard parts, both are well-documented here.

---

## 5. Metadata and Tagging

### Metadata Providers

Komga uses a plugin-style interface (`BookMetadataProvider`, `SeriesMetadataProvider`, `SeriesMetadataFromBookProvider`) where each provider generates a `BookMetadataPatch` or `SeriesMetadataPatch`. The applier (`MetadataApplier.kt`) merges patches into the stored metadata, skipping any field that is locked.

| Provider | Source | Book metadata | Series metadata | Controlled by |
|---|---|---|---|---|
| `ComicInfoProvider` | `ComicInfo.xml` inside CBZ/ZIP | title, summary, number, numberSort, releaseDate, authors, tags, isbn, links, readLists | title, publisher, ageRating, language, genres, collections, readingDirection | `library.importComicInfoBook` / `Series` / `ReadList` / `Collection` |
| `EpubMetadataProvider` | EPUB OPF package file | title, summary, releaseDate, authors, isbn, number (from `group-position`) | series title (from `belongs-to-collection`), publisher, language, genres, readingDirection | `library.importEpubBook` / `importEpubSeries` |
| `MylarSeriesProvider` | `series.json` sidecar | — | title (with volume/year disambiguator), status, publisher, ageRating, language, genres, totalBookCount, url | `library.importMylarSeries` |
| `OneShotSeriesProvider` | Book metadata aggregation | — | title, summary, totalBookCount=1, status=ENDED | always (for oneshot series) |
| `IsbnBarcodeProvider` | Image barcode scan (ZXing) | isbn | — | `library.importBarcodeIsbn` |
| `LocalArtworkProvider` | Image files in same directory | — (thumbnails only) | — (thumbnails only) | `library.importLocalArtwork` |

### ComicInfo.xml Fields (Full mapping)

`ComicInfoProvider.kt` reads from `ComicInfo.xml` (found via `MEDIA_FILE` table entry):

| ComicInfo Field | Maps to |
|---|---|
| `Series` | `SeriesMetadataPatch.title` (optionally appended with volume) |
| `Volume` | Appended to series title if `importComicInfoSeriesAppendVolume` and volume != 1 |
| `Title` | `BookMetadataPatch.title` |
| `Number` | `BookMetadataPatch.number` (string), `numberSort` (float via `toFloatOrNull()`) |
| `Count` | `SeriesMetadataPatch.totalBookCount` |
| `Year`/`Month`/`Day` | `BookMetadataPatch.releaseDate` |
| `Writer`/`Penciller`/`Inker`/`Colorist`/`Letterer`/`CoverArtist`/`Editor`/`Translator` | `BookMetadataPatch.authors` with corresponding role strings |
| `Publisher` | `SeriesMetadataPatch.publisher` |
| `AgeRating` | `SeriesMetadataPatch.ageRating` |
| `LanguageISO` | `SeriesMetadataPatch.language` (validated as BCP-47) |
| `Genre` | `SeriesMetadataPatch.genres` (comma-separated) |
| `Tags` | `BookMetadataPatch.tags` (comma-separated, lowercased) |
| `Summary` | `BookMetadataPatch.summary` |
| `Manga` (NO/YES_AND_RIGHT_TO_LEFT) | `SeriesMetadataPatch.readingDirection` |
| `SeriesGroup` | `SeriesMetadataPatch.collections` (comma-separated) |
| `AlternateSeries` / `AlternateNumber` | `BookMetadataPatch.readLists` |
| `StoryArc` / `StoryArcNumber` | `BookMetadataPatch.readLists` (multiple arcs, comma-split, paired with numbers) |
| `GTIN` | `BookMetadataPatch.isbn` (validated by Apache Commons Validator) |
| `Web` | `BookMetadataPatch.links` (space-separated URLs) |

### Lock Flags

Every metadata field has a corresponding `*Lock` boolean in the DB. When locked:
- Metadata providers cannot overwrite the field.
- The field is only updated by explicit user edits via the REST API.
- Locked fields survive book moves/renames (`tryRestoreBooks` preserves locked titles).

### Metadata Aggregation

`BookMetadataAggregation` (`BOOK_METADATA_AGGREGATION` table) stores aggregated values computed from all books in a series:
- `RELEASE_DATE` (earliest or latest — **[inference]**: likely first), `SUMMARY`, `SUMMARY_NUMBER`
- `BOOK_METADATA_AGGREGATION_AUTHOR`, `BOOK_METADATA_AGGREGATION_TAG` — union of all book-level authors/tags

### Smart Filters (Search Conditions)

`SearchCondition.kt` defines a sealed class hierarchy of composable filter conditions:
- **Boolean combinators**: `AllOfBook`, `AnyOfBook`, `AllOfSeries`, `AnyOfSeries`
- **Book conditions**: `LibraryId`, `ReadListId`, `SeriesId`, `Deleted`, `OneShot`, `Title`, `ReleaseDate`, `Tag`, `NumberSort`, `ReadStatus`, `MediaStatus`, `MediaProfile`, `Author`, `Poster`
- **Series conditions**: `LibraryId`, `CollectionId`, `Deleted`, `Complete`, `OneShot`, `Title`, `TitleSort`, `ReleaseDate`, `Tag`, `SharingLabel`, `Publisher`, `Language`, `Genre`, `AgeRating`, `ReadStatus`, `SeriesStatus`, `Author`

These are translated to jOOQ SQL by repository implementations and exposed to the REST API as JSON.

### Content Restrictions

Per-user content filtering (`ContentRestrictions.kt`, stored in `USER` table):
- `ageRestriction`: `{age: Int, restriction: ALLOW_ONLY | EXCLUDE}` — filter by series `ageRating`
- `labelsAllow`: whitelist of sharing labels (series must have at least one)
- `labelsExclude`: blacklist of sharing labels
- `sharingLabels` on `SeriesMetadata`: per-series labels set by admins for content control

**Relevance to lychee**: The ComicInfo.xml field mapping is the industry standard — implement it first. The lock-flag pattern is essential for a server that both auto-imports and allows manual edits. The `SearchCondition` DSL is sophisticated but worth emulating as a typed filter system. SQLite FTS5 (already in the engine) can replace Lucene for basic full-text search, avoiding the complexity of a separate index directory.

---

## 6. Media Scan and Filename Structure

### Scan Pipeline Step-by-Step

1. **`FileSystemScanner.scanRootFolder()`** (`FileSystemScanner.kt`):
   - Walks the library root with `Files.walkFileTree(..., FOLLOW_LINKS, MAX_VALUE, ...)`.
   - `preVisitDirectory`: records every directory as a tentative Series. Skips directories starting with `.` or matching any `directoryExclusions` pattern.
   - `visitFile`: matches extensions (`cbz`, `zip`, `cbr`, `rar`, `pdf`, `epub`); collects sidecar candidates. Creates `Book(name=nameWithoutExtension, url=filePath, fileLastModified, fileSize)`.
   - `postVisitDirectory`: if the directory has books:
     - One-shot check: if `oneshotsDirectory` is a non-null, non-blank string and the directory path contains it → each book becomes its own `Series`.
     - Normal: associates all books with the directory's `Series`. Matches book sidecar candidates to actual books.

2. **`LibraryContentLifecycle.scanRootFolder()`**: reconciles scan results against DB (see Section 3).

3. **`SeriesLifecycle.sortBooks()`**: sorts books by filename (natural sort → strips accents, collapses whitespace) and assigns `BOOK.NUMBER` (1-based ordinal). Also updates `BOOK_METADATA.NUMBER` and `NUMBER_SORT` to the ordinal as floats (unless locked).

4. **Analysis** (triggered as tasks): `BookAnalyzer.analyze()` determines media type via Tika, then dispatches to `analyzeDivina()`, `analyzePdf()`, or `analyzeEpub()`.

### Expected Directory Layouts

```
<Library root>/
  My Manga Series/          ← Series directory
    My Manga Series v01.cbz ← Book 1
    My Manga Series v02.cbz ← Book 2
  Another Series/
    Chapter 001.zip
    Chapter 001.5.zip       ← fractional chapter
  Oneshots/                 ← oneshotsDirectory = "Oneshots"
    Akira.cbz               ← becomes its own Series "Akira"
    Lone Wolf and Cub.epub  ← becomes its own Series
```

Subdirectories within a series are **not** natively supported — every directory is a separate Series. The scanner goes one level deep per directory conceptually but creates Series for every directory that contains books.

### Filename Parsing

Komga does **not** parse filenames with regexes to extract volume/chapter numbers. The filename is used only for:
- `Book.name` = `path.nameWithoutExtension` (raw)
- **Ordering**: natural sort of `Book.name` (via `CaseInsensitiveSimpleNaturalComparator`)
- The ordinal position (1, 2, 3...) after sort becomes both `BOOK.NUMBER` and the default `BOOK_METADATA.NUMBER_SORT`

Number/chapter information comes entirely from **metadata providers** (ComicInfo.xml, EPUB OPF). If no metadata is embedded, the book's display number defaults to its natural-sort position.

Natural sort behavior: `"v1", "v2", "v10"` sorts as `v1 < v2 < v10` (not `v1 < v10 < v2` as in lexicographic sort). `"Chapter 1.5"` sorts between `"Chapter 1"` and `"Chapter 2"`. This is the sole filename-based ordering mechanism.

### Sidecar Matching

Series sidecars: exact filename match against a known list (e.g. `series.json` for Mylar, `cover.jpg` for artwork). `SidecarSeriesConsumer.getSidecarSeriesFilenames()`.

Book sidecars: two-step:
1. Prefilter: regex list from `SidecarBookConsumer.getSidecarBookPrefilter()` reduces candidates
2. Exact match: `SidecarBookConsumer.isSidecarBookMatch(bookBaseName, sidecarName)` — for local artwork, checks if sidecar name (without extension) matches the book's `nameWithoutExtension` (optionally with `-\d+` suffix for multiple covers)

**Relevance to lychee**: The no-regex-filename-parsing decision is a pragmatic choice — metadata files are authoritative. Python's `natsort` library handles natural sort. The sidecar pattern is clean and worth adopting. Consider adding optional filename regex parsing as a library-level opt-in feature for users without embedded metadata.

---

## 7. Image Decoding and Archives

### Container Formats

| Format | Extensions | Library | Notes |
|---|---|---|---|
| ZIP | `.cbz`, `.zip` | Apache Commons Compress `ZipFile` | Content sorted by natural sort before analysis |
| RAR v4 | `.cbr`, `.rar` | junrar 7.6.0 | Throws `MediaUnsupportedException` for encrypted (ERR_1002), multi-volume (ERR_1004), solid (ERR_1003) archives |
| RAR v5 | `.cbr`, `.rar` | nightcompress 1.1.1 (native JNI) | Registered conditionally via `Rar5Configuration.postProcessBeanDefinitionRegistry()` only if `Archive.isAvailable()` returns true |
| PDF | `.pdf` | Apache PDFBox 3.0.5 | Pages rendered on-the-fly via `PDFRenderer`; page content stored as synthetic `BookPage` with empty `mediaType` |
| EPUB | `.epub` | Custom extractor using java.util.zip | Handles standard EPUB 2/3, fixed-layout EPUB (Divina-compatible), KEPUB (Kobo format) |

Note: there is no 7z/CB7 support.

### Image Formats

All image I/O goes through Java's `ImageIO` SPI framework. Plugins registered:

| Format | Plugin | Notes |
|---|---|---|
| JPEG | TwelveMonkeys imageio-jpeg 3.12.0 | Replaces default, better spec compliance |
| TIFF | TwelveMonkeys imageio-tiff | |
| WebP | Both TwelveMonkeys imageio-webp AND nightmonkeys/imageio-webp | `ImageConverter.chooseWebpReader()` deregisters all but nightmonkeys at startup |
| JXL | nightmonkeys/imageio-jxl 1.0.0 | JPEG XL |
| HEIF/AVIF | nightmonkeys/imageio-heif 1.0.0 | HEIF/AVIF via libheif |
| JPEG 2000 | jai-imageio-jpeg2000 1.4.0 | |
| JBIG2 | pdfbox/jbig2-imageio 3.0.4 | Used in PDF scan |
| PNG, GIF | JDK built-in | |

**Write formats**: only JPEG and PNG (`ImageType` enum: `PNG("image/png", "PNG")`, `JPEG("image/jpeg", "JPEG")`). All thumbnail output is in one of these two formats.

### Page Extraction and Ordering

- **ZIP/CBZ/RAR**: `DivinaExtractor.getEntries()` returns all entries; filtered to those where `ContentDetector.isImage(mediaType)` is true; sorted by natural sort on entry name.
- **PDF**: `PdfExtractor.getPages()` returns synthetic entries named `"1"`, `"2"`, etc. (no actual image yet); `getPageContentAsImage()` renders on demand at configurable DPI (`pdfResolution`).
- **EPUB**: `EpubExtractor.getDivinaPages()` returns pages only for fixed-layout EPUBs (where pages are images); for reflowable EPUBs, pages are virtual positions computed by `computePositions()`.

The `ContentDetector.detectMediaType()` uses Tika to sniff MIME type from bytes (not file extension). This is how CBZ files are identified as `application/zip` even if named `.cbz`.

### Cover / Thumbnail Generation

`BookAnalyzer.generateThumbnail()`:
1. Calls `getPoster()` to get the first page bytes and MIME type.
2. Resizes via `ImageConverter.resizeImageToByteArray()` using Thumbnailator.
3. Target: `thumbnailType` bean (JPEG by default), max edge size from `ThumbnailSize` enum.

`ThumbnailSize` enum (`ThumbnailSize.kt`):
```kotlin
enum class ThumbnailSize(val maxEdge: Int) {
    DEFAULT(300), MEDIUM(600), LARGE(900), XLARGE(1200)
}
```
The default server thumbnail size is configured in `SERVER_SETTINGS` (stored in DB).

**Storage**: `THUMBNAIL_BOOK`, `THUMBNAIL_SERIES`, `THUMBNAIL_COLLECTION`, `THUMBNAIL_READLIST` tables. Each row stores either:
- `THUMBNAIL` (blob) — the resized JPEG/PNG bytes directly in SQLite
- `URL` (varchar) — path to a sidecar image file on disk (for `Type.SIDECAR`)

Thumbnail types: `GENERATED` (from first page, auto-created), `SIDECAR` (local artwork file), `USER_UPLOADED` (user manually uploaded).

Additional thumbnail metadata columns (added in `V20231005165322`): `WIDTH`, `HEIGHT`, `MEDIA_TYPE`, `FILE_SIZE`.

### On-the-Fly Conversion and Streaming

- **Format conversion** (`ImageConverter.convertImage()`): reads source bytes, writes in target format. Handles alpha channel removal for non-transparent targets (fills with white).
- **Resize** (`ImageConverter.resizeImageToByteArray()`): uses Thumbnailator `Thumbnails.of(...).size(resizeTo, resizeTo).imageType(ARGB).outputFormat(format)`. Does not upscale (capped at source longest edge).
- **PDF rendering**: on-demand per page via `PDFRenderer.renderImage(pageIndex, scale, RGB)` using PDFBox; no caching — rendered fresh each request. Scale derived from page's `cropBox` dimensions and configured DPI.
- **WebP reader conflict**: Komga explicitly deregisters all WebP `ImageReaderSpi` providers except the nightmonkeys one, since TwelveMonkeys also provides a WebP reader (`ImageConverter.chooseWebpReader()`).

### Corrupt/Encrypted Archive Handling

- Encrypted RAR: detected by `rar.isPasswordProtected` → `MediaUnsupportedException("ERR_1002")` → `Media.status = UNSUPPORTED`.
- Multi-volume RAR: detected by `rar.mainHeader.isMultiVolume` → `MediaUnsupportedException("ERR_1004")`.
- `AccessDeniedException`, `NoSuchFileException` → specific error codes (ERR_1000, ERR_1018).
- Any other exception during analysis → `Media.status = ERROR`, `comment = "ERR_1005"`.
- Entries that fail within an archive: logged as warnings; stored with null `mediaType`; reported in `Media.comment` as `ERR_1007 [filename1, filename2]`.
- Books with zero pages: `Media.status = ERROR, comment = "ERR_1006"`.

**Relevance to lychee**: The archive library choices are critical. For Python: `zipfile` (stdlib) for CBZ, `rarfile` (Python wrapper around unrar) for CBR, `pdfplumber`/`pypdf` for PDF, `ebooklib` for EPUB. For image I/O: Pillow handles JPEG/PNG/WebP/GIF; `pillow-heif` adds HEIF/AVIF; `imageio` + plugins for TIFF/JXL. Thumbnail caching as BLOBs in SQLite is valid for small deployments; for larger ones, consider storing thumbnails as files in a `~/.lychee/thumbnails/` directory (use content-addressed naming so renaming doesn't break them). PDF rendering on-demand is fine but slow — consider a thumbnail cache table (SQLite BLOB) for rendered PDF pages.

---

## Notable Design Decisions, Tradeoffs, and Gotchas

### Two SQLite Databases

Main data and task queue are in separate files (`database.sqlite`, `tasks.sqlite`). This avoids lock contention between the task processor (which hammers the tasks DB) and normal read queries. Each has its own jOOQ schema generated independently at build time.

### SQLite SQLITE_TOOBIG Limit

CHANGELOG note (commit `d34d4a5`): "cap search results to avoid SQLITE_TOOBIG". SQLite has a 1 MB limit on SQL statement size; Lucene ID results passed as `IN (...)` lists can exceed this if uncapped. **[gotcha]** In lychee, use `LIMIT` on Lucene result sets before passing to SQL, or use a temp table approach.

### Lucene vs SQLite FTS5 (Historical Decision)

SQLite FTS5 tables were added in August 2021 and removed 9 days later in favor of Lucene (`V20210727102041` → `V20210805174355`). The reason (from CHANGELOG): FTS5 was not flexible enough for multilingual n-gram analysis and lacked the filtering/sorting power needed for smart search. Lucene's n-gram tokenizer enables partial-word matching across languages (important for Japanese/Chinese/Korean manga titles). **[lychee note]** SQLite FTS5 is still a valid first implementation for English-only or ASCII-heavy collections; add Lucene/Tantivy later if needed.

### XXH3-128 Hash Migration

Originally used MD5 for file and page hashing; migrated to XXH3-128 in `V20230626150454__xxhash128.sql`, which resets all existing hashes (forces re-hash of everything on next scan). XXH3-128 is ~10x faster than MD5 for large files. The migration note: KOReader hash stays as partial MD5 because that's what KOReader itself uses.

### Soft Delete / Trash Bin

Books and series are never immediately deleted from DB on disk removal — they get `deletedDate` set. This enables the move/rename restore logic. The `EMPTY_TRASH` task or manual trigger permanently deletes them. This is critical for preserving read progress when users reorganize their libraries.

### No File Watching

Komga deliberately uses polling (periodic scans) rather than OS file watching. File watching via JVM `WatchService` has known reliability issues on NFS/SMB mounts (common for NAS-based libraries). The comment in `LibraryContentLifecycle.kt` acknowledges NFS/SMB cache issues explicitly (line 141: "can be used to detect changed series even if their file modified date did not change, for example because of NFS/SMB cache").

### EPUB Complexity

EPUB analysis is the most complex path: extracts TOC, landmarks, page list, divina pages, computes R2 positions, detects KEPUB format, counts pages (either image count for fixed-layout or computed position count for reflowable). A re-analysis is triggered when the EPUB extension format changes (`V20231214163213__reanalyze_epub.sql`).

### Mylar series.json

Mylar is a comic management tool that stores series metadata in `series.json` sidecar files. Komga reads these as an optional series metadata provider. The `series.json` is detected as a `SidecarSeriesConsumer`-matched file during the scan.

### Session Storage

Spring Session is Caffeine-backed (in-memory, `spring-session-caffeine 2.1.0`), not DB-backed. This means sessions do not survive server restarts — users must log in again after a restart. (There was a SQLite-backed session store added in `V20210907115532__spring_session.sql` and then removed in `V20211006141333__remove_spring_session.sql` — presumably due to performance issues.)

### `forceDirectoryModifiedTime` Option

`library.scanForceModifiedTime` — when true, the series `fileLastModified` is set to `max(directoryMtime, max(bookMtime))`. This handles SMB/NFS shares that don't update directory mtime when a file inside changes (a very common edge case).

---

## File Index

Key files referenced in this analysis:

| Path | Purpose |
|---|---|
| `komga/build.gradle.kts` | All dependency versions and jOOQ/Flyway configuration |
| `gradle/libs.versions.toml` | Version catalog (lucene, sqlite-jdbc, twelvemonkeys, nightmonkeys, springboot, jooq) |
| `gradle.properties` | Komga version (1.25.0) |
| `DEVELOPING.md` | Dev setup, Spring profiles, Gradle tasks |
| `ERRORCODES.md` | Error code catalogue |
| `komga/src/flyway/resources/db/migration/sqlite/V20200706141854__initial_migration.sql` | Initial schema (LIBRARY, USER, SERIES, SERIES_METADATA, BOOK, MEDIA, MEDIA_PAGE, MEDIA_FILE, BOOK_METADATA, BOOK_METADATA_AUTHOR, READ_PROGRESS, COLLECTION, COLLECTION_SERIES) |
| `komga/src/flyway/resources/tasks/migration/sqlite/V20231013114850__tasks.sql` | Task queue schema |
| `komga/src/flyway/resources/db/migration/sqlite/V20240529120934__syncpoint.sql` | Kobo sync point schema |
| `komga/src/flyway/resources/db/migration/sqlite/V20250108115503__user_roles.sql` | USER_ROLE table migration |
| `komga/src/flyway/resources/db/migration/sqlite/V20230724114349__oneshots.sql` | One-shot columns |
| `komga/src/flyway/resources/db/migration/sqlite/V20231206152158__progression.sql` | R2Locator on ReadProgress |
| `komga/src/flyway/resources/db/migration/sqlite/V20250108172343__koreader_hash.sql` | KOReader hash column |
| `komga/src/main/kotlin/org/gotson/komga/domain/model/Book.kt` | Book entity |
| `komga/src/main/kotlin/org/gotson/komga/domain/model/Series.kt` | Series entity |
| `komga/src/main/kotlin/org/gotson/komga/domain/model/Media.kt` | Media entity + status enum |
| `komga/src/main/kotlin/org/gotson/komga/domain/model/MediaType.kt` | Supported container types enum |
| `komga/src/main/kotlin/org/gotson/komga/domain/model/BookMetadata.kt` | Book metadata with lock flags |
| `komga/src/main/kotlin/org/gotson/komga/domain/model/SeriesMetadata.kt` | Series metadata with lock flags |
| `komga/src/main/kotlin/org/gotson/komga/domain/model/ReadProgress.kt` | Read progress entity |
| `komga/src/main/kotlin/org/gotson/komga/domain/model/Library.kt` | Library entity with all options |
| `komga/src/main/kotlin/org/gotson/komga/domain/model/ThumbnailBook.kt` | Thumbnail entity (GENERATED/SIDECAR/USER_UPLOADED) |
| `komga/src/main/kotlin/org/gotson/komga/domain/model/ThumbnailSize.kt` | Thumbnail size presets |
| `komga/src/main/kotlin/org/gotson/komga/domain/model/UserRoles.kt` | ADMIN/FILE_DOWNLOAD/PAGE_STREAMING/KOBO_SYNC/KOREADER_SYNC |
| `komga/src/main/kotlin/org/gotson/komga/domain/model/SearchCondition.kt` | Composable filter DSL |
| `komga/src/main/kotlin/org/gotson/komga/domain/model/DomainEvent.kt` | All domain events (for SSE push) |
| `komga/src/main/kotlin/org/gotson/komga/domain/service/FileSystemScanner.kt` | Filesystem walk + Series/Book creation |
| `komga/src/main/kotlin/org/gotson/komga/domain/service/LibraryContentLifecycle.kt` | Scan reconciliation, move detection |
| `komga/src/main/kotlin/org/gotson/komga/domain/service/SeriesLifecycle.kt` | sortBooks (natural sort → ordinal assignment) |
| `komga/src/main/kotlin/org/gotson/komga/domain/service/BookAnalyzer.kt` | Archive analysis, thumbnail generation, page extraction |
| `komga/src/main/kotlin/org/gotson/komga/application/tasks/Task.kt` | All task types with priority constants |
| `komga/src/main/kotlin/org/gotson/komga/application/tasks/TaskEmitter.kt` | Task submission API |
| `komga/src/main/kotlin/org/gotson/komga/application/tasks/TaskProcessor.kt` | Thread pool task consumption |
| `komga/src/main/kotlin/org/gotson/komga/application/scheduler/LibraryScanScheduler.kt` | Per-library periodic scan scheduler |
| `komga/src/main/kotlin/org/gotson/komga/infrastructure/hash/Hasher.kt` | XXH3-128 file/stream hashing |
| `komga/src/main/kotlin/org/gotson/komga/infrastructure/hash/KoreaderHasher.kt` | Partial MD5 KOReader hash |
| `komga/src/main/kotlin/org/gotson/komga/infrastructure/mediacontainer/ContentDetector.kt` | Tika MIME detection |
| `komga/src/main/kotlin/org/gotson/komga/infrastructure/mediacontainer/divina/ZipExtractor.kt` | ZIP/CBZ extraction |
| `komga/src/main/kotlin/org/gotson/komga/infrastructure/mediacontainer/divina/RarExtractor.kt` | RAR4 extraction (junrar) |
| `komga/src/main/kotlin/org/gotson/komga/infrastructure/mediacontainer/divina/Rar5Extractor.kt` | RAR5 extraction (nightcompress, conditional) |
| `komga/src/main/kotlin/org/gotson/komga/infrastructure/mediacontainer/pdf/PdfExtractor.kt` | PDF page extraction + rendering (PDFBox) |
| `komga/src/main/kotlin/org/gotson/komga/infrastructure/image/ImageConverter.kt` | Image resize/convert (Thumbnailator + ImageIO) |
| `komga/src/main/kotlin/org/gotson/komga/infrastructure/image/ImageType.kt` | JPEG / PNG thumbnail target types |
| `komga/src/main/kotlin/org/gotson/komga/infrastructure/metadata/comicrack/ComicInfoProvider.kt` | ComicInfo.xml parser |
| `komga/src/main/kotlin/org/gotson/komga/infrastructure/metadata/epub/EpubMetadataProvider.kt` | EPUB OPF metadata parser (Jsoup) |
| `komga/src/main/kotlin/org/gotson/komga/infrastructure/metadata/mylar/MylarSeriesProvider.kt` | Mylar series.json parser |
| `komga/src/main/kotlin/org/gotson/komga/infrastructure/metadata/oneshot/OneShotSeriesProvider.kt` | One-shot series metadata |
| `komga/src/main/kotlin/org/gotson/komga/infrastructure/metadata/localartwork/LocalArtworkProvider.kt` | Local image sidecar matching |
| `komga/src/main/kotlin/org/gotson/komga/infrastructure/search/LuceneConfiguration.kt` | Lucene index + search manager setup |
| `komga/src/main/kotlin/org/gotson/komga/infrastructure/search/LuceneEntity.kt` | Lucene document field definitions |
| `komga/src/main/kotlin/org/gotson/komga/infrastructure/security/SecurityConfiguration.kt` | Full auth configuration |
| `komga/src/main/kotlin/org/gotson/komga/interfaces/api/kosync/KoreaderSyncController.kt` | KOReader sync endpoints |
| `komga/src/main/kotlin/org/gotson/komga/interfaces/api/kobo/KoboController.kt` | Kobo device sync endpoints |
| `komga/src/main/kotlin/org/gotson/komga/interfaces/api/opds/v1/OpdsController.kt` | OPDS 1.2 Atom XML catalog |
| `komga/src/main/kotlin/org/gotson/komga/interfaces/api/opds/v2/Opds2Controller.kt` | OPDS 2.0 JSON catalog |
| `komga/src/main/kotlin/org/gotson/komga/interfaces/api/WebPubGenerator.kt` | WebPub Manifest (Divina/EPUB/PDF) |
| `komga/src/main/kotlin/org/gotson/komga/interfaces/sse/SseController.kt` | Server-Sent Events push |
| `komga/src/main/resources/application.yml` | Default config (port 25600, config-dir, DB paths, Lucene path) |
