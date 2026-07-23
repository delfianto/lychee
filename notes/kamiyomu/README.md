# KamiYomu — Deep-Dive Code Analysis

Analysis performed: 2026-07-23  
Source: `/Users/dwi.elfianto/workspace/github/lychee/temp/KamiYomu`  
Commit: shallow clone, single branch (`main`)

---

## Quick Facts

| Property | Value |
|---|---|
| Language / Runtime | C# / .NET 8 |
| Web framework | ASP.NET Core 8 — Razor Pages + MVC Controllers (mixed) |
| Database engine | **LiteDB 5** (embedded document store — NOT SQLite, NOT EF Core) |
| Background jobs | **Hangfire 1.8** with SQLite storage (`Hangfire.Storage.SQLite 0.4.2`) |
| Image processing | **SkiaSharp 3.119** |
| PDF generation | **QuestPDF 2025.7** |
| Primary archive format | CBZ (ZIP) — created by `System.IO.Compression.ZipFile` |
| Caching | **MonkeyCache.LiteDB 2.1** (key-value TTL cache backed by LiteDB) |
| Real-time UI | **SignalR** (notification hub) |
| Frontend | HTMX + Bootstrap — no SPA framework |
| API surface | OPDS 1.2 (Atom/XML), versioned REST API (Swagger/OpenAPI), no GraphQL |
| Auth | Optional HTTP Basic Auth middleware (single admin user, plaintext credentials in config) |
| Plugin model | NuGet-distributed C# assemblies loaded via `AssemblyLoadContext` |
| Docker | Official `Dockerfile`, Chromium bundled in container image |
| License | AGPL-3.0 |
| Maturity | Early/active — single-user, crawler-first orientation |

**TL;DR.** KamiYomu is a crawler-centric manga downloader + reader, not a scan-and-index server. It stores metadata and images exclusively via LiteDB (a .NET embedded document database). There is no schema migration system (no EF Core). Content enters the system only via a Hangfire background job calling a plugin-loaded C# crawler assembly. The local file store is CBZ (ZIP), served directly from disk. Reading progress is tracked per-page. No multi-user concept, no external metadata scraping from AniList/MangaDex/etc. — all metadata comes from the crawler plugin itself.

---

## Section 1 — Stack

### .NET version and web framework

- `<TargetFramework>net8.0</TargetFramework>` — `src/KamiYomu.Web/KamiYomu.Web.csproj` line 3.
- ASP.NET Core 8 with both **Razor Pages** (UI) and **MVC Controllers** (REST API area called `Public`).
- `Program.cs` delegates everything into typed extension classes under `Infrastructure/Hostings/`.
- Listens on `http://*:8080` (Kestrel, `appsettings.json`).

### ORM and database

- **No EF Core, no SQL database, no migrations.**
- `LiteDB 5.0.21` — embedded document/BSON store.
- Four separate LiteDB files:

| File | Context class | Purpose |
|---|---|---|
| `/db/main.db` | `DbContext` | `CrawlerAgent`, `Library`, `UserPreference`, `NugetSource` collections |
| `/db/image.db` | `ImageDbContext` | Cover image binary storage (`ILiteStorage<Uri>`) |
| `/db/reading.db` | `ReadingDbContext` | `ChapterProgress` read-progress records |
| `/db/worker.db` | Hangfire SQLite | Background job queue (via `sqlite-net-pcl`) |
| `/db/lib{Guid}.db` | `LibraryDbContext` | Per-manga `MangaDownloadRecord` + `ChapterDownloadRecord` |

Source: `Infrastructure/Contexts/DbContext.cs`, `LibraryDbContext.cs`, `ImageDbContext.cs`, `Areas/Reader/Data/ReadingDbContext.cs`, `Infrastructure/Hostings/WorkerJobsHostings.cs`.

Each context opens a `LiteDatabase` with `ConnectionType.Shared` (shared-lock mode). There are no schema migrations — schema evolves from collection names only.

### Key NuGet packages

```
Hangfire.AspNetCore              1.8.22
Hangfire.Storage.SQLite          0.4.2
LiteDB                           5.0.21
MonkeyCache.LiteDB               2.1.1
SkiaSharp                        3.119.1
SkiaSharp.NativeAssets.Linux     3.119.1
QuestPDF                         2025.7.4
Swashbuckle.AspNetCore           10.1.2
Asp.Versioning.Mvc               8.1.1
Serilog.AspNetCore               10.0.0
Microsoft.Extensions.Localization 10.0.0
Polly                            8.6.5
Microsoft.Extensions.Http.Polly  10.0.0
KamiYomu.CrawlerAgents.Core      1.1.4   (custom SDK, published to packages.kamiyomu.com)
NuGet.Versioning                 7.0.1
HarfBuzzSharp.NativeAssets.Linux 8.3.1.2
```

Source: `KamiYomu.Web.csproj`.

### Background jobs and scheduling

Hangfire with SQLite storage. Three named job queues plus internal queues:

- `download-chapter-queue-1` — `IChapterDownloaderJob` (downloads individual CBZ from crawler)
- `manga-download-scheduler-queue-1` — `IMangaDownloaderJob` (enumerates chapters, enqueues chapter downloads)
- `discovery-new-chapter-queue-1` — `IChapterDiscoveryJob` (recurring daily: polls crawler for new chapters)
- `deferred-execution-queue` — `DeferredExecutionCoordinator` (every 5 min: re-enqueues stale jobs)
- `notification-queue` — `INotifyKavitaJob` (debounced Kavita scan trigger)

The Hangfire dashboard is exposed at `/worker` with `AllowAllDashboardAuthorizationFilter` (no auth). Job retry: up to `MaxRetryAttempts` (default 10), then `AttemptsExceededAction.Delete`.

Source: `Infrastructure/Hostings/WorkerJobsHostings.cs`, `Infrastructure/Services/WorkerService.cs`.

### API style

- **REST JSON API** under `/public/api/v1/` — versioned with `Asp.Versioning`, documented via Swagger at `/public/api/swagger/index.html`.
- **OPDS 1.2** Atom/XML feed at `/public/api/v1/opds` — custom `AtomXmlResult<T>` serializer; supports manga list, chapter list, and chapter download links (CBZ, ZIP, EPUB, PDF).
- **Razor Pages** serve the HTML UI (no SPA; HTMX for partial updates).
- **SignalR** hub at `/notificationHub` for real-time toast notifications.

Source: `Areas/Public/Controllers/OpdsController.cs`, `Areas/Public/PublicHoistingExtension.cs`, `Hubs/NotificationHub.cs`.

### Authentication

Optional HTTP Basic Auth (`BasicAuthMiddleware`) — a single admin username and password in `appsettings.json` under `BasicAuth`. When disabled (default), the app is fully open. Passwords are stored plaintext in config. No session, no JWT, no cookie auth. The Hangfire dashboard has no auth at all (separate filter: `AllowAllDashboardAuthorizationFilter`).

Source: `Middlewares/BasicAuthMiddleware.cs`, `AppOptions/BasicAuthOptions.cs`.

### Build and dev run

```
dotnet restore
dotnet build
dotnet run
```

Frontend static assets managed via LibMan CLI (`libman.json`). Docker multi-stage build (SDK 8 → aspnet 8 runtime). LibMan restores Bootstrap, HTMX, etc. into `wwwroot`.

### Deployment (Docker)

`src/docker-compose.yml` + `src/KamiYomu.Web/Dockerfile`. The Dockerfile:
1. Installs Chromium and required shared libraries.
2. Creates a non-root `KamiYomu` user (UID 1000).
3. Mounts four persistent Docker volumes: `/manga`, `/db`, `/logs`, `/agents`.
4. `HEALTHCHECK` hits `/healthz`.

SkiaSharp Linux native assets and HarfBuzzSharp are included as NuGet packages to support image rendering inside the container without additional system libs.

**Relevance to lychee:** LiteDB as the primary store is an unusual choice (most Python projects would use SQLite + SQLAlchemy). For lychee, SQLAlchemy + SQLite is the right call — it has proper migration tooling (Alembic), a mature Python ecosystem, and is less opaque than a document store. Hangfire's queue-per-concern pattern (separate queues for discovery vs. chapter download vs. notification) is worth replicating with Celery or ARQ. The LibMan static-asset pipeline has no Python equivalent — use a standard `npm`/`vite` or just serve pre-built assets.

---

## Section 2 — Media Management Model

### Domain hierarchy

KamiYomu's domain is: **CrawlerAgent → Library (Manga) → Chapters → Pages**. There is no concept of "library" as a folder hierarchy: each `Library` represents a single manga title tracked against one crawler agent.

```
CrawlerAgent    — a plugin assembly (one per website/source)
Library         — one manga in the collection; keyed to one CrawlerAgent
  Manga         — inline object (embedded in Library): title, id, coverUrl, authors, tags, etc.
  MangaDownloadRecord  — tracks the download job for the manga (per-library DB)
  ChapterDownloadRecord — tracks each chapter download job (per-library DB)
    Chapter     — inline: number (decimal), volume (decimal), title, id, uri, pages
      Page      — ephemeral (not persisted): page number, image URL
```

There is **no explicit concept** of:
- Library as a directory of multiple series
- Series/book/one-shot distinctions
- Volumes as first-class entities
- Collections spanning multiple series (only single-manga Libraries)

### Entity definitions

**`Library`** (`Entities/Library.cs`):
```csharp
public Guid Id { get; private set; }
public CrawlerAgent CrawlerAgent { get; private set; }
public Manga Manga { get; private set; }
public string? FilePathTemplate { get; private set; }        // e.g. "{manga_title}/{manga_title} Ch.{chapter_padded_4}"
public string? ComicInfoTitleTemplateFormat { get; private set; }
public string? ComicInfoSeriesTemplate { get; private set; }
public DateTimeOffset CreatedDate { get; private set; }
```

**`Manga`** (defined in `KamiYomu.CrawlerAgents.Core` NuGet — not in this repo's source). Properties referenced throughout the codebase:
```
Id, Title, CoverUrl (Uri), Authors (list), Artists (list), Tags (list),
OriginalLanguage (string), IsFamilySafe (bool), WebSiteUrl (string)
```

**`Chapter`** (also in Core):
```
Id, Number (decimal), Volume (decimal), Title, Uri, ParentManga
```

**`ChapterDownloadRecord`** (`Entities/ChapterDownloadRecord.cs`):
```csharp
public Guid Id { get; }
public CrawlerAgent CrawlerAgent { get; }
public MangaDownloadRecord MangaDownload { get; }
public Chapter Chapter { get; }           // embedded; contains Number (decimal), Volume (decimal)
public string BackgroundJobId { get; }
public DateTimeOffset CreateAt { get; }
public DateTimeOffset? StatusUpdateAt { get; }
public DownloadStatus DownloadStatus { get; }   // enum: 0-4
public string? StatusReason { get; }
```

**`MangaDownloadRecord`** (`Entities/MangaDownloadRecord.cs`):
```csharp
public Guid Id { get; }
public string BackgroundJobId { get; }
public Library Library { get; }
public DateTimeOffset CreateAt { get; }
public DateTimeOffset? StatusUpdateAt { get; }
public DownloadStatus DownloadStatus { get; }
public string? StatusReason { get; }
```

**LiteDB collections** (actual "tables"):
- `main.db` / `agent_crawlers` — `CrawlerAgent` documents
- `main.db` / `libraries` — `Library` documents (with nested `Manga`, `CrawlerAgent`)
- `main.db` / `user_preferences` — `UserPreference`
- `main.db` / `nuget_sources` — `NugetSource`
- `main.db` / `_agent_crawler_file_storage` + `_packages` — binary NuGet package blobs
- `image.db` / `_cover_image_file_store` + `_cover_images` — binary cover images
- `reading.db` / `chapter_progress` — `ChapterProgress`
- `lib{guid}.db` / `chapter_download_records`, `manga_download_records` — per-manga records

Source: `Infrastructure/Contexts/DbContext.cs` lines 49-53, `LibraryDbContext.cs` lines 12-13, `ImageDbContext.cs` line 46, `Areas/Reader/Data/ReadingDbContext.cs` line 40.

### Chapter numbers

Chapter number and volume number are both `decimal` (`Chapter.Number`, `Chapter.Volume`). The `TemplateResolver` handles decimal padding correctly (e.g., `{chapter_padded_4}` → `0001.5` for chapter 1.5). Previous/next chapter navigation uses `Number - 1` and `Number + 1` integer math, which breaks for decimal chapters like 1.5 (inference: this is a known limitation).

Source: `Infrastructure/Services/TemplateResolver.cs` lines 141-165, `Areas/Reader/Pages/MangaReader/Index.cshtml.cs` lines 66-71.

### No volume/collection concept

There is no `Volume` entity. Volume number is a property on `Chapter`. There is no "one-shot" vs. "series" distinction — everything is a series with chapters. Collections at the UI level show all `Library` entries.

**Relevance to lychee:** The flat model (Library = one manga) is very simple. lychee will likely need a richer hierarchy (Library → Series → Volume → Chapter) for proper shelf organization. The `decimal` chapter number approach is correct and should be adopted. The per-library-DB design in KamiYomu (splitting download records into `lib{guid}.db`) is clever for isolation but complex — lychee should use a single SQLite DB with proper foreign keys.

---

## Section 3 — File Management and Sync

### How content enters the system

KamiYomu is a **crawler-first downloader**, not a scanner. Files are created by the app itself:

1. User searches a crawler for a manga.
2. User clicks "Add to collection" → `DownloadAppService.AddToCollectionAsync()` creates a `Library` record and a `MangaDownloadRecord`, then schedules a `MangaDownloaderJob`.
3. `MangaDownloaderJob` paginates through the crawler's chapter list, creates `ChapterDownloadRecord` per chapter, enqueues `ChapterDownloaderJob` per chapter.
4. `ChapterDownloaderJob` downloads each page image via `HttpClient`, writes to a temp folder, creates `ComicInfo.xml`, then calls `ZipFile.CreateFromDirectory()` to produce the CBZ file.

Source: `Infrastructure/AppServices/DownloadAppService.cs`, `Worker/MangaDownloaderJob.cs`, `Worker/ChapterDownloaderJob.cs`.

### File layout on disk

Default template: `{manga_title}/{manga_title} Ch.{chapter_padded_4}.cbz`

Example: `/manga/Attack on Titan/Attack on Titan Ch.0001.cbz`

Configurable per-library via `FilePathTemplate`. Template variables:
- `{manga_title}`, `{manga_title_slug}`
- `{chapter}`, `{chapter_padded_1}` through `{chapter_padded_5}`
- `{chapter_title}`, `{chapter_title_slug}`
- `{volume}`, `{volume_padded_1}` through `{volume_padded_5}`
- `{date}`, `{datetime}`, `{year}`, `{month}`, `{day}`, etc.

Source: `AppOptions/SpecialFolderOptions.cs`, `Infrastructure/Services/TemplateResolver.cs`.

### Change detection and consistency

- **No filesystem watcher.** No `FileSystemWatcher` is registered anywhere.
- **No hash/dedupe.** KamiYomu does not compute checksums.
- **Sync mechanism:** `ChapterDiscoveryJob` (daily recurring) re-enumerates chapters from the crawler and checks `File.Exists(library.GetCbzFilePath(chapter))`. If the file exists, it marks the record as completed and skips. If missing, it creates/updates a record and enqueues a new download. This means: if a file is manually deleted, the next daily discovery will re-download it.
- **Orphan handling:** If the `Library` record is deleted (`RemoveFromCollectionAsync`), the per-library LiteDB file (`lib{guid}.db`) is deleted. CBZ files on disk are NOT automatically deleted (the user must clean them manually).

Source: `Worker/ChapterDiscoveryJob.cs` lines 53-109, `Infrastructure/AppServices/DownloadAppService.cs` lines 69-94.

### Stale detection

`MangaDownloadRecord.IsStale()` and `ChapterDownloadRecord.IsStale()` return `true` if status is `InProgress` and `StatusUpdateAt` is more than 24 hours ago (`AddDays(-1)`). The `DeferredExecutionCoordinator` (every 5 min) re-enqueues past-due Hangfire jobs.

Source: `Entities/MangaDownloadRecord.cs` line 60, `Entities/ChapterDownloadRecord.cs` line 125.

### Add / remove / reschedule

- **Add:** `POST /public/api/v1/crawler-agent/download-content` (or UI dialog) → `DownloadAppService.AddToCollectionAsync()`.
- **Remove:** `DELETE /public/api/v1/collection/{libraryId}` → cancels Hangfire jobs, deletes `lib{guid}.db`, removes `Library` from `main.db`. CBZ files remain on disk.
- **Reschedule chapter:** `PATCH /public/api/v1/collection/{libraryId}/chapters/{chapterId}/reschedule` → deletes existing CBZ file, re-enqueues download.

Source: `Areas/Public/Controllers/CollectionController.cs`, `Areas/Public/Controllers/CrawlerAgentController.cs`.

**Relevance to lychee:** lychee plans to scan existing local files, which is the opposite approach. The template-based path generation is clean and worth adopting. The "check File.Exists before re-downloading" pattern is a practical consistency check that lychee should also implement. The lack of a watcher means new external files are not picked up automatically — lychee should add an inotify/watchdog watcher or at least a periodic scan trigger.

---

## Section 4 — Reading Tracker

### Read-progress model

`ChapterProgress` (`Areas/Reader/Models/ChapterProgress.cs`):

```csharp
public Guid Id { get; }
public Guid LibraryId { get; }
public Guid ChapterDownloadId { get; }    // FK to ChapterDownloadRecord
public decimal ChapterNumber { get; }
public int LastPageRead { get; }
public DateTimeOffset LastReadAt { get; set; }
public bool IsCompleted { get; }
public int TotalPages { get; }
```

Progress is tracked **per-page, per-chapter**. When a page scrolls into view (HTMX `hx-trigger="page-passed"`), the reader POSTs to `OnPostPageViewed()` which upserts a `ChapterProgress` record. When the last page is reached, `IsCompleted` is set to `true`.

On next visit, `LastReadPage` is restored from the stored record and the reader scrolls to that position.

Source: `Areas/Reader/Pages/MangaReader/Index.cshtml.cs` lines 62-92, `Areas/Reader/Models/ChapterProgress.cs`.

### Storage

`ChapterProgress` records live in `/db/reading.db` → LiteDB collection `chapter_progress`. There is no separate index — LiteDB uses its own internal B-tree.

### Multi-user

**No multi-user support.** There is a single `UserPreference` document for the whole app. `ChapterProgress` has no user ID. All progress is global. Basic Auth provides a single admin login, but there is no user-level data partitioning.

### External sync (KOReader, Tachiyomi, AniList, MAL, OPDS-PS)

- **OPDS:** Standard OPDS 1.2 catalog — compatible with Moon+ Reader, KyBook, etc. for download. No OPDS Push-to-Server (OPDS-PS).
- **Kavita integration:** When a chapter is downloaded, a debounced Hangfire job (`NotifyKavitaJob`) calls Kavita's `/api/Library/scan-all` endpoint. KamiYomu can authenticate to Kavita via API key or username/password. This is **push notification only** — it tells Kavita to rescan its library, not vice versa.
- **Gotify integration:** Push notifications (title downloaded, search completed) via Gotify REST API.
- **No KOReader sync, no Tachiyomi/Mihon sync, no AniList/MAL integration.**

Source: `Infrastructure/Services/KavitaService.cs`, `Infrastructure/Services/GotifyService.cs`, `Worker/NotifyKavitaJob.cs`, `Entities/UserPreferences.cs`.

**Relevance to lychee:** The per-page progress tracking (scroll-triggered HTMX POST) is an elegant low-overhead pattern. For lychee, a REST endpoint for progress update is the right approach. Multi-user is absent here but is explicitly needed for lychee. OPDS is present and worth implementing. KOReader sync (via sync server protocol) and AniList tracking are absent — lychee should plan for these. Kavita integration model (outbound webhook) is easy to replicate.

---

## Section 5 — Metadata and Tagging

### Metadata model

Metadata originates **entirely from the crawler plugin**. The `Manga` and `Chapter` objects are returned by the `ICrawlerAgent` interface from the `KamiYomu.CrawlerAgents.Core` NuGet package. KamiYomu itself does **not scrape external sources** — it delegates to the plugin.

Properties visible on `Manga` (inferred from usage throughout codebase):

| Property | Type | Source |
|---|---|---|
| `Id` | `string` | Crawler-specific |
| `Title` | `string` | Crawler |
| `CoverUrl` | `Uri` | Crawler |
| `Authors` | `IEnumerable<string>` | Crawler |
| `Artists` | `IEnumerable<string>` | Crawler |
| `Tags` | `IEnumerable<string>` | Crawler |
| `OriginalLanguage` | `string` | Crawler |
| `IsFamilySafe` | `bool` | Crawler |
| `WebSiteUrl` | `string` | Crawler |

There is no `Description`, `Status` (ongoing/completed), `AlternativeTitles`, `PublicationYear`, `Rating` or similar on the stored model (these would have to come from the crawler).

### ComicInfo.xml generation

When downloading a chapter, KamiYomu generates a `ComicInfo.xml` file and includes it in the CBZ ZIP. The generation is in `Library.ToComicInfo(Chapter chapter)`:

```csharp
XElement comicInfo = new("ComicInfo",
    new XElement("Title",        /* ComicInfoTitleTemplate resolved */),
    new XElement("Series",       /* ComicInfoSeriesTemplate resolved */),
    new XElement("Number",       chapter.Number.ToString()),
    new XElement("Volume",       chapter.Volume.ToString()),
    new XElement("Writer",       string.Join(", ", manga.Authors)),
    new XElement("Penciller",    string.Join(", ", manga.Artists)),
    new XElement("CoverArtist",  string.Join(", ", manga.Artists)),
    new XElement("LanguageISO",  manga.OriginalLanguage),
    new XElement("Genre",        string.Join(", ", manga.Tags)),
    new XElement("ScanInformation", "KamiYomu"),
    new XElement("Web",          chapter.Uri or manga.WebSiteUrl),
    new XElement("AgeRating",    manga.IsFamilySafe ? "Everyone" : "Adult"),
    new XElement("Notes",        /* JSON serialization of full Chapter object */)
);
```

Source: `Entities/Library.cs` lines 224-244.

KamiYomu **writes** ComicInfo.xml but does **not read/parse** existing ComicInfo.xml from pre-existing CBZ files. There is no EPUB OPF parsing either.

### External metadata scraping

**None.** KamiYomu does not query AniList, MangaUpdates, MangaDex, or any external metadata DB. All data comes from the crawler plugin only.

### Manual metadata editing / locking / refresh

**None.** There is no UI to edit manga metadata post-import. No field locking. Metadata refresh is implicit: when a chapter is re-discovered, the crawler re-fetches `Manga` metadata (cached for 30 min via `MonkeyCache`).

### Tags, genres, collections

- `Tags`/`Genres` come from the crawler as a `string[]` on `Manga`.
- No user-defined tags.
- No collection grouping beyond the single-manga `Library` concept.
- `FamilySafeMode` (a boolean on `UserPreference`) filters display of manga where `IsFamilySafe == false`.

### Search and filter

The `CollectionController.List` endpoint supports a simple `?search=` parameter that does a `Contains` match on `Manga.Title` (LiteDB LINQ query). No full-text search, no tag filter, no sort parameter.

Source: `Areas/Public/Controllers/CollectionController.cs` lines 44-53.

**Relevance to lychee:** The absence of metadata scraping is the biggest gap. lychee should implement ComicInfo.xml parsing on ingest (for existing CBZ libraries) and optional AniList/MangaUpdates matching. The ComicInfo.xml format KamiYomu writes is standard — adopt the same schema for interoperability. The tag/filter story is weak here; lychee needs faceted search (by genre, author, status, language).

---

## Section 6 — Media Scan and Filename Structure

### Scan pipeline

KamiYomu does **not scan the filesystem for existing files** to build a catalog. The pipeline is:

1. User searches the crawler for a manga title.
2. User adds the manga → `Library` record created.
3. `MangaDownloaderJob` asks the crawler for chapter list (paginated, 30 chapters/page).
4. For each chapter, `ChapterDownloaderJob` downloads pages and creates the CBZ.
5. `ChapterDiscoveryJob` runs daily: asks crawler for chapter list, checks `File.Exists()` for each, re-queues missing chapters.

There is **no directory scanner**, no filename parser, no "import existing files" feature.

### Expected directory layout

```
/manga/
  {manga_title}/
    {manga_title} Ch.{chapter_padded_4}.cbz
    ...
```

Example:
```
/manga/
  Attack on Titan/
    Attack on Titan Ch.0001.cbz
    Attack on Titan Ch.0002.cbz
    Attack on Titan Ch.0001.5.cbz    (decimal chapters supported)
```

The path and filename are controlled by `FilePathTemplate`. The template is resolved by `TemplateResolver.Resolve()` and `FileNameHelper.SanitizeFileName()` normalizes accented characters and strips path-invalid chars.

### Filename parsing

KamiYomu does **not parse filenames**. The chapter number is known from the crawler's `Chapter.Number` property, not extracted from the filename. There are no regex parsers for filenames.

### Ordering

Within a series, chapters are ordered by `Chapter.Number` (ascending). In the reader, previous/next chapter is `Number - 1` / `Number + 1` (integer lookup, which fails for decimal gaps like 1.5 → 2).

Source: `Areas/Reader/Pages/MangaReader/Index.cshtml.cs` lines 66-71, `ChapterDownloaderJob.cs` line 119 (`pages.OrderBy(p => p.PageNumber)`).

**Relevance to lychee:** lychee must implement a proper filename parser since it scans existing local libraries rather than creating files itself. The chapter number padding conventions here (4 or 5 digits, decimal-aware) are the same as Kavita/Komga/Tachiyomi conventions and should be adopted. lychee will need regex-based parsers similar to Kavita's for patterns like `Ch.0001`, `Chapter 1`, `Vol.1 Ch.2`, etc.

---

## Section 7 — Image Decoding and Archives

### Container formats

| Format | Support | How |
|---|---|---|
| CBZ (ZIP) | Primary | `System.IO.Compression.ZipFile` / `ZipArchive` — read and write |
| ZIP | Aliases to CBZ | Same file, served with `application/zip` MIME |
| EPUB | Export only | Built in-memory from CBZ contents — `ZipArchive` |
| PDF | Export only | Via `QuestPDF` — images extracted from CBZ, rendered page-by-page |
| CBR (RAR) | **Not supported** | |
| 7z | **Not supported** | |
| EPUB ingest | **Not supported** | |
| Folder | Not supported | |

All content is stored as CBZ. The reader reads images directly from the CBZ stream.

Source: `Infrastructure/Services/ZipService.cs`, `Infrastructure/Services/EpubService.cs`, `Infrastructure/Services/PdfService.cs`, `Areas/Reader/Pages/MangaReader/Index.cshtml.cs`.

### Image formats

Supported in the reader (read from CBZ):
- `.jpg` / `.jpeg`
- `.png`
- `.webp`

Supported in PDF generation:
- `.jpg`, `.jpeg`, `.png`, `.bmp`, `.webp`

Source: `Areas/Reader/Pages/MangaReader/Index.cshtml.cs` lines 40-45, `Infrastructure/Services/PdfService.cs` lines 46-53.

### Image libraries

- **SkiaSharp 3.119** — listed as a NuGet dependency and used via `HarfBuzzSharp.NativeAssets.Linux` for text/font rendering in QuestPDF. SkiaSharp itself is not called directly in the application code visible here (it may be a transitive dep of QuestPDF).
- **QuestPDF** — used to generate PDF exports. Images are loaded from filesystem paths and embedded in the PDF document.
- No ImageSharp, no Magick.NET, no System.Drawing.

Source: `KamiYomu.Web.csproj` lines 41-60, `Infrastructure/Services/PdfService.cs`.

### Page extraction and ordering

The reader (`IndexModel.OnGet`) opens the CBZ with `ZipFile.OpenRead`, filters entries by extension, excludes `cover.*` files, and sorts by `FullName` (lexicographic). Pages are served one-by-one as individual HTTP responses via `OnGetImage()` — each image is read from the ZIP into a `MemoryStream` and returned as a `File()` result.

Source: `Areas/Reader/Pages/MangaReader/Index.cshtml.cs` lines 37-52.

### Cover and thumbnail generation

Cover images are downloaded directly from `Manga.CoverUrl` by `ChapterDownloaderJob.SaveCoverAsync()` and stored into:

1. The first chapter's temp folder (as `cover.{ext}`) before CBZ creation.
2. `ImageDbContext` — `_cover_image_file_store` / `_cover_images` (LiteDB file storage, keyed by `Uri`).

Cover images are served from LiteDB binary storage through a URL-to-internal image URL conversion (`UriExtensions.ToInternalImageUrl()`). There is no thumbnail generation (no resizing, no WebP conversion, no multiple sizes). Images are served at original resolution.

Source: `Worker/ChapterDownloaderJob.cs` lines 216-245, `Infrastructure/Contexts/ImageDbContext.cs` line 46.

### On-the-fly conversion / resize

**None.** Images are served as-is from the CBZ archive. No transcoding, no resizing, no WebP conversion.

### Large / corrupt / encrypted archives

- A minimum file count check is performed after CBZ creation (`numberOfFiles <= 2` → warning + re-throw). Source: `Worker/ChapterDownloaderJob.cs` lines 143-157.
- No handling for corrupt ZIP entries or encrypted archives.
- No streaming reads for very large archives (entire entry is copied to `MemoryStream`).

**Relevance to lychee:** The `ZipFile.OpenRead` + serve from `MemoryStream` pattern is simple but memory-intensive for large archives. lychee should stream images directly from the ZIP without loading the entire page into memory. Python's `zipfile` module supports streaming. CBR (RAR) support is commonly needed for legacy manga collections — lychee should add it via `rarfile` or `python-unrar`. The lack of thumbnail/resize is a UX limitation; lychee should generate WebP thumbnails at ingest time and cache them.

---

## Notable Design Decisions, Tradeoffs, and Gotchas

### Design decisions

1. **LiteDB over SQLite+ORM:** Avoids schema migration complexity. The document model fits plugin-returned `Manga`/`Chapter` objects well. Trade-off: no SQL queries, no joins, harder to debug, no standard migration tooling. The per-library DB (`lib{guid}.db`) isolates chapter records but fragments the database across many files.

2. **Plugin-first architecture:** Crawler agents are NuGet packages loaded via `AssemblyLoadContext`. This enables community-contributed crawlers without forking the core. The `KamiYomu.CrawlerAgents.Core` package defines the `ICrawlerAgent` interface. The `CrawlerAgentDecorator` pattern wraps the loaded instance to handle cross-context interface cast issues.

3. **No filesystem scanner:** The app creates its own files and knows exactly what exists. This is simpler than scanning but means the app can't import an existing local library. This is an explicit design choice for a downloader, not a reader-first app.

4. **HTMX for dynamic UI:** Avoids SPA complexity. Page updates are partial HTML swaps. The reader's progress tracking (HTMX `hx-trigger="page-passed"`) is creative — scroll-based events trigger invisible HTMX POSTs.

5. **Hangfire for background jobs:** Pragmatic choice. The Hangfire dashboard at `/worker` provides job visibility. The `DeferredExecutionCoordinator` (re-enqueuing past-due jobs every 5 min) compensates for potential Hangfire scheduling drift.

6. **Rate limiting built into worker:** `WorkerOptions.MinWaitPeriodInMilliseconds` / `MaxWaitPeriodInMilliseconds` (default: 3–7 seconds random delay between page downloads) prevents hammering source sites.

### Gotchas

- **No migration path for LiteDB schema changes.** Adding a field to `Library` requires a code-only approach (LiteDB stores BSON, missing fields default to null/zero).
- **Per-library DB proliferation.** Each manga gets its own `lib{guid}.db`. With hundreds of titles, this becomes many files. LiteDB shared-connection mode means concurrent reads require careful handling.
- **Integer-based prev/next chapter navigation** breaks for decimal chapter numbers (e.g., chapter 1.5 followed by chapter 2 — `1.5 + 1 = 2.5`, which won't match chapter 2).
- **No HTTPS.** Kestrel listens on HTTP only. HTTPS requires an external reverse proxy.
- **Hangfire dashboard is unauthenticated.** Anyone on the network can see job details and trigger actions.
- **Cover image served from LiteDB binary storage** — not from disk. Cover images are duplicated (in the CBZ archive + in `image.db`).
- **EPUB export is minimal.** The generated EPUB has no proper TOC, no reading direction metadata, and wraps each image in a bare XHTML page. Page direction is hardcoded to `rtl`.
- **SkiaSharp is a dependency but appears unused** in the app code (likely pulled in transitively by QuestPDF or for font rendering).
- **Single-user only.** Adding multi-user would require rearchitecting `ChapterProgress` (add user ID), `UserPreference` (per-user), and the auth layer.

---

## Appendix: Full Template Variable Reference

From `Infrastructure/Services/TemplateResolver.cs`:

**Manga variables:** `{manga_title}`, `{manga_title_slug}`, `{manga_familysafe}`  
**Chapter variables:** `{chapter}`, `{chapter_padded_1}` – `{chapter_padded_5}`, `{chapter_title}`, `{chapter_title_slug}`, `{volume}`, `{volume_padded_1}` – `{volume_padded_5}`  
**Date/time variables:** `{date}`, `{date_short}`, `{date_compact}`, `{time}`, `{time_compact}`, `{datetime}`, `{datetime_compact}`, `{year}`, `{month}`, `{day}`, `{hour}`, `{minute}`, `{second}`

---

## Summary: Relevance to lychee

| Topic | KamiYomu approach | lychee recommendation |
|---|---|---|
| Database | LiteDB (document store, no migrations) | SQLAlchemy + SQLite (relational, Alembic migrations) — already planned, correct |
| Background jobs | Hangfire with named queues | Celery or ARQ with named queues (same pattern) |
| File ingest | Crawler-creates files; no scanner | Filesystem scanner + inotify watcher (opposite approach — implement) |
| Filename parsing | Not needed (crawler provides metadata) | Implement regex-based parser (series/volume/chapter from filename) |
| Archive formats | CBZ read+write, EPUB/PDF export only | CBZ, CBR, 7z, EPUB, PDF input; CBZ/EPUB export |
| Image serving | Per-image HTTP response from MemoryStream | Stream directly from archive; generate WebP thumbnails at ingest |
| Reading progress | Per-page, single-user, LiteDB | Per-page + per-chapter, multi-user, SQLite foreign-keyed to users |
| External metadata | None (crawler only) | AniList, MangaUpdates, MangaDex scraping + ComicInfo.xml parser |
| OPDS | OPDS 1.2 implemented | Implement OPDS 1.2 + consider OPDS-PS |
| Auth | Single-user Basic Auth | Per-user JWT or session auth from day 1 |
| Notifications | SignalR (WebSocket) + Gotify push | SSE or WebSocket; optional Gotify/Apprise |
| Kavita integration | Outbound library rescan trigger | Optional outbound webhook model |
| ComicInfo.xml | Write on download | Read on import + write on export |
| Chapter numbers | `decimal` — correct | `decimal` — adopt |
| Rate limiting | Random delay between page downloads | Implement crawl rate limiting (if lychee adds crawler support) |
