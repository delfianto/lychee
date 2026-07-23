# Komga SQLite Schema Reference

All tables are in `database.sqlite` unless noted. Source files are under `komga/src/flyway/resources/db/migration/sqlite/` and `komga/src/flyway/kotlin/db/migration/sqlite/`. Columns are listed in order of introduction (initial + additive migrations).

---

## Core Tables

### LIBRARY
Source: `V20200706141854__initial_migration.sql`, extended by many subsequent migrations.

| Column | Type | Notes |
|---|---|---|
| ID | varchar PK | TSID-256 |
| CREATED_DATE | datetime | |
| LAST_MODIFIED_DATE | datetime | |
| NAME | varchar | Display name |
| ROOT | varchar | Filesystem root path (URL) |
| IMPORT_COMICINFO_BOOK | boolean | Default 1 |
| IMPORT_COMICINFO_SERIES | boolean | Default 1 |
| IMPORT_COMICINFO_COLLECTION | boolean | Default 1 |
| IMPORT_EPUB_BOOK | boolean | Default 1 |
| IMPORT_EPUB_SERIES | boolean | Default 1 |
| IMPORT_COMICINFO_READLIST | boolean | Added V20200817 |
| IMPORT_LOCAL_ARTWORK | boolean | Added V20200814 |
| IMPORT_MYLAR_SERIES | boolean | Added V20210716 |
| SCAN_FORCE_MODIFIED_TIME | boolean | Added V20210504 |
| CONVERT_TO_CBZ | boolean | Added V20210504 |
| REPAIR_EXTENSIONS | boolean | Added V20210505 |
| EMPTY_TRASH_AFTER_SCAN | boolean | Added V20210706 |
| UNAVAILABLE_DATE | datetime NULL | Added V20210816 |
| COVER_PREFERENCE | varchar | Added V20210726 (FIRST/FIRST_UNREAD_OR_FIRST/etc.) |
| HASH_FILES | boolean | Added V20220105 |
| HASH_PAGES | boolean | Added V20220105 |
| ONESHOTS_DIRECTORY | varchar NULL | Added V20230724 |
| SCAN_STARTUP | boolean | Added V20230918 |
| SCAN_CBX | boolean | Added V20230918 |
| SCAN_PDF | boolean | Added V20230918 |
| SCAN_EPUB | boolean | Added V20230918 |
| SCAN_INTERVAL | varchar | Added V20230918 (DISABLED/HOURLY/EVERY_6H/etc.) |
| IMPORT_COMICINFO_SERIES_APPEND_VOLUME | boolean | Added V20230112 |
| IMPORT_BARCODE_ISBN | boolean | Added V20220101 |
| DIRECTORY_EXCLUSIONS | text | Added V20230921 |
| ANALYZE_DIMENSIONS | boolean | Added V20200730 |
| HASH_KOREADER | boolean | Added V20250108 |

### SERIES
Source: `V20200706141854__initial_migration.sql`

| Column | Type | Notes |
|---|---|---|
| ID | varchar PK | TSID-256 |
| CREATED_DATE | datetime | |
| LAST_MODIFIED_DATE | datetime | |
| FILE_LAST_MODIFIED | datetime | max(ctime, mtime) of directory |
| NAME | varchar | Directory name |
| URL | varchar | Directory path as URL |
| LIBRARY_ID | varchar FK→LIBRARY | |
| BOOK_COUNT | int | Added V20210526 (denormalized) |
| DELETED_DATE | datetime NULL | Added V20210706 (soft delete) |
| ONESHOT | boolean | Added V20230724 |

### SERIES_METADATA
Source: `V20200706141854__initial_migration.sql`, extended by many migrations.

| Column | Type | Notes |
|---|---|---|
| SERIES_ID | varchar PK FK→SERIES | |
| CREATED_DATE | datetime | |
| LAST_MODIFIED_DATE | datetime | |
| STATUS | varchar | ENDED/ONGOING/ABANDONED/HIATUS |
| STATUS_LOCK | boolean | |
| TITLE | varchar | |
| TITLE_LOCK | boolean | |
| TITLE_SORT | varchar | |
| TITLE_SORT_LOCK | boolean | |
| SUMMARY | varchar | Added V20200820 |
| SUMMARY_LOCK | boolean | Added V20200820 |
| READING_DIRECTION | varchar NULL | Added V20200820 |
| READING_DIRECTION_LOCK | boolean | Added V20200820 |
| PUBLISHER | varchar | Added V20200820 |
| PUBLISHER_LOCK | boolean | Added V20200820 |
| AGE_RATING | int NULL | Added V20200820 |
| AGE_RATING_LOCK | boolean | Added V20200820 |
| LANGUAGE | varchar | Added V20200820 |
| LANGUAGE_LOCK | boolean | Added V20200820 |
| GENRES_LOCK | boolean | Added V20200820 |
| TAGS_LOCK | boolean | Added V20200820 |
| TOTAL_BOOK_COUNT | int NULL | Added V20210729 |
| TOTAL_BOOK_COUNT_LOCK | boolean | Added V20210729 |
| SHARING_LABELS_LOCK | boolean | Added V20220224 |
| LINKS_LOCK | boolean | Added V20230113 |
| ALTERNATE_TITLES_LOCK | boolean | Added V20230116 |

Related tables: `SERIES_METADATA_GENRE`, `SERIES_METADATA_TAG`, `SERIES_METADATA_SHARING_LABEL`, `SERIES_METADATA_LINK`, `SERIES_METADATA_ALTERNATE_TITLE`

### BOOK
Source: `V20200706141854__initial_migration.sql`

| Column | Type | Notes |
|---|---|---|
| ID | varchar PK | TSID-256 |
| CREATED_DATE | datetime | |
| LAST_MODIFIED_DATE | datetime | |
| FILE_LAST_MODIFIED | datetime | max(ctime, mtime) of file |
| NAME | varchar | Filename without extension |
| URL | varchar | File path as URL |
| SERIES_ID | varchar FK→SERIES | |
| FILE_SIZE | int8 | bytes |
| NUMBER | int | 1-based ordinal in series (natural sort order) |
| LIBRARY_ID | varchar FK→LIBRARY | |
| DELETED_DATE | datetime NULL | Added V20210706 (soft delete) |
| FILE_HASH | varchar | Added V20220105, XXH3-128 hex |
| ONESHOT | boolean | Added V20230724 |
| FILE_HASH_KOREADER | varchar | Added V20250108, partial MD5 |

### BOOK_METADATA
Source: `V20200706141854__initial_migration.sql`

| Column | Type | Notes |
|---|---|---|
| BOOK_ID | varchar PK FK→BOOK | |
| CREATED_DATE | datetime | |
| LAST_MODIFIED_DATE | datetime | |
| TITLE | varchar | |
| TITLE_LOCK | boolean | |
| SUMMARY | varchar | |
| SUMMARY_LOCK | boolean | |
| NUMBER | varchar | Display label e.g. "1.5" |
| NUMBER_LOCK | boolean | |
| NUMBER_SORT | real | Float sort key |
| NUMBER_SORT_LOCK | boolean | |
| RELEASE_DATE | date NULL | |
| RELEASE_DATE_LOCK | boolean | |
| AUTHORS_LOCK | boolean | |
| PUBLISHER | varchar | |
| PUBLISHER_LOCK | boolean | |
| READING_DIRECTION | varchar NULL | |
| READING_DIRECTION_LOCK | boolean | |
| AGE_RATING | int NULL | |
| AGE_RATING_LOCK | boolean | |
| ISBN | varchar | Added V20210308 |
| ISBN_LOCK | boolean | Added V20210308 |
| TAGS_LOCK | boolean | Added V20200820 |
| LINKS_LOCK | boolean | Added V20211228 |

Related: `BOOK_METADATA_AUTHOR` (NAME, ROLE, BOOK_ID), `BOOK_METADATA_TAG`, `BOOK_METADATA_LINK`

### BOOK_METADATA_AGGREGATION
Source: `V20210111113543__book_metadata_aggregation.sql`

| Column | Type | Notes |
|---|---|---|
| SERIES_ID | varchar PK FK→SERIES | |
| CREATED_DATE | datetime | |
| LAST_MODIFIED_DATE | datetime | |
| RELEASE_DATE | date NULL | |
| SUMMARY | varchar | |
| SUMMARY_NUMBER | varchar | |

Related: `BOOK_METADATA_AGGREGATION_AUTHOR`, `BOOK_METADATA_AGGREGATION_TAG`

---

## Media Tables

### MEDIA
Source: `V20200706141854__initial_migration.sql`

| Column | Type | Notes |
|---|---|---|
| BOOK_ID | varchar PK FK→BOOK | |
| CREATED_DATE | datetime | |
| LAST_MODIFIED_DATE | datetime | |
| STATUS | varchar | UNKNOWN/ERROR/READY/UNSUPPORTED/OUTDATED |
| MEDIA_TYPE | varchar NULL | MIME string (e.g. "application/zip") |
| PAGE_COUNT | int | |
| COMMENT | varchar NULL | Error code string |
| EPUB_DIVINA_COMPATIBLE | boolean | Added V20231214 |
| EPUB_IS_KEPUB | boolean | Added V20240911 |
| EXTENSION_CLASS | varchar NULL | Added V20231116 (MediaExtensionEpub class name) |
| EXTENSION_VALUE | varchar NULL | Added V20231116 (JSON blob of extension) |

### MEDIA_PAGE
Source: `V20200706141854__initial_migration.sql`

| Column | Type | Notes |
|---|---|---|
| BOOK_ID | varchar FK→BOOK | |
| NUMBER | int | 1-based page number |
| FILE_NAME | varchar | Entry name within archive |
| MEDIA_TYPE | varchar | MIME of image |
| WIDTH | int | Added V20200730 |
| HEIGHT | int | Added V20200730 |
| FILE_SIZE | int8 NULL | Added V20220106 |
| FILE_HASH | varchar | Added V20220101, XXH3-128 |
| PK | (BOOK_ID, NUMBER) | |

### MEDIA_FILE
Source: `V20200706141854__initial_migration.sql`

| Column | Type | Notes |
|---|---|---|
| BOOK_ID | varchar FK→BOOK | |
| FILE_NAME | varchar | Entry name in archive (e.g. "ComicInfo.xml") |
| MEDIA_TYPE | varchar NULL | Added V20231116 |
| SUB_TYPE | varchar NULL | Added V20231116 |
| FILE_SIZE | int8 NULL | Added V20231116 |

---

## Thumbnail Tables

### THUMBNAIL_BOOK
Source: `V20200810154729__thumbnails_part_1.sql`

| Column | Type | Notes |
|---|---|---|
| ID | varchar PK | TSID-256 |
| BOOK_ID | varchar FK→BOOK | |
| CREATED_DATE | datetime | |
| LAST_MODIFIED_DATE | datetime | |
| THUMBNAIL | blob NULL | Image bytes (JPEG/PNG) |
| URL | varchar NULL | Sidecar image file path |
| SELECTED | boolean | Is this the chosen thumbnail? |
| TYPE | varchar | GENERATED/SIDECAR/USER_UPLOADED |
| WIDTH | int | Added V20231005 |
| HEIGHT | int | Added V20231005 |
| MEDIA_TYPE | varchar | Added V20231005 |
| FILE_SIZE | int8 | Added V20231005 |

### THUMBNAIL_SERIES, THUMBNAIL_COLLECTION, THUMBNAIL_READLIST
Same structure as `THUMBNAIL_BOOK` but with `SERIES_ID`, `COLLECTION_ID`, `READLIST_ID` FKs respectively.

### PAGE_HASH
Source: `V20220128152310__page_hash.sql`

| Column | Type | Notes |
|---|---|---|
| HASH | varchar | XXH3-128 hex |
| MEDIA_TYPE | varchar | Image MIME |
| SIZE | int8 NULL | File size of the page |
| ACTION | varchar | DELETE/IGNORE |
| DELETE_COUNT | int | |
| CREATED_DATE | datetime | |
| LAST_MODIFIED_DATE | datetime | |
| PK | (HASH, MEDIA_TYPE, SIZE) | |

### PAGE_HASH_THUMBNAIL
Source: `V20220128152310__page_hash.sql`

| Column | Type | Notes |
|---|---|---|
| HASH | varchar | |
| MEDIA_TYPE | varchar | |
| SIZE | int8 NULL | |
| THUMBNAIL | blob | |
| PK | (HASH, MEDIA_TYPE, SIZE) | |

---

## Collection / ReadList Tables

### COLLECTION
Source: `V20200706141854__initial_migration.sql`

| Column | Type | |
|---|---|---|
| ID | varchar PK | |
| NAME | varchar | |
| ORDERED | boolean | |
| SERIES_COUNT | int | Denormalized |
| CREATED_DATE | datetime | |
| LAST_MODIFIED_DATE | datetime | |
| SUMMARY | varchar | Added V20210730 |

### COLLECTION_SERIES
| Column | Type | |
|---|---|---|
| COLLECTION_ID | varchar FK→COLLECTION | |
| SERIES_ID | varchar FK→SERIES | |
| NUMBER | int | Position in ordered collection |
| PK | (COLLECTION_ID, SERIES_ID) | |

### READLIST
Source: `V20200817115957__readlists.sql`

| Column | Type | |
|---|---|---|
| ID | varchar PK | |
| NAME | varchar | |
| BOOK_COUNT | int | Denormalized |
| CREATED_DATE | datetime | |
| LAST_MODIFIED_DATE | datetime | |
| SUMMARY | varchar | Added V20210730 |
| ORDERED | boolean | Added V20230221 (default true) |

### READLIST_BOOK
| Column | Type | |
|---|---|---|
| READLIST_ID | varchar FK→READLIST | |
| BOOK_ID | varchar FK→BOOK | |
| NUMBER | int | Position in list |
| PK | (READLIST_ID, BOOK_ID) | |

---

## User Tables

### USER
Source: `V20200706141854__initial_migration.sql`, rebuilt in `V20250108115503__user_roles.sql`

| Column | Type | Notes |
|---|---|---|
| ID | varchar PK | TSID-256 |
| CREATED_DATE | datetime | |
| LAST_MODIFIED_DATE | datetime | |
| EMAIL | varchar UNIQUE | |
| PASSWORD | varchar | BCrypt hash |
| SHARED_ALL_LIBRARIES | boolean | Default 1 |
| AGE_RESTRICTION | integer NULL | Added V20220225 |
| AGE_RESTRICTION_ALLOW_ONLY | boolean NULL | Added V20220225 |

### USER_ROLE
Source: `V20250108115503__user_roles.sql`

| Column | Type | |
|---|---|---|
| USER_ID | varchar FK→USER | |
| ROLE | varchar | ADMIN/FILE_DOWNLOAD/PAGE_STREAMING/KOBO_SYNC/KOREADER_SYNC |
| PK | (USER_ID, ROLE) | |

### USER_LIBRARY_SHARING
| Column | Type | |
|---|---|---|
| USER_ID | varchar FK→USER | |
| LIBRARY_ID | varchar FK→LIBRARY | |
| PK | (USER_ID, LIBRARY_ID) | |

### USER_API_KEY
Source: `V20240529120933__apikey.sql`

| Column | Type | |
|---|---|---|
| ID | varchar PK | |
| USER_ID | varchar FK→USER | |
| CREATED_DATE | datetime | |
| LAST_MODIFIED_DATE | datetime | |
| API_KEY | varchar UNIQUE | Hashed with XXH3-128 |
| COMMENT | varchar | User-supplied label |

---

## Read Progress

### READ_PROGRESS
Source: `V20200706141854__initial_migration.sql`, extended

| Column | Type | Notes |
|---|---|---|
| BOOK_ID | varchar FK→BOOK | |
| USER_ID | varchar FK→USER | |
| CREATED_DATE | datetime | |
| LAST_MODIFIED_DATE | datetime | |
| PAGE | int | Last read page (1-based) |
| COMPLETED | boolean | |
| READ_DATE | datetime NULL | Added V20210914 |
| DEVICE_ID | varchar | Added V20231206, default '' |
| DEVICE_NAME | varchar | Added V20231206, default '' |
| LOCATOR | blob NULL | Added V20231206, JSON R2Locator |
| PK | (BOOK_ID, USER_ID) | |

### READ_PROGRESS_SERIES
Source: `V20210526113555__series_book_count.sql`

| Column | Type | Notes |
|---|---|---|
| SERIES_ID | varchar FK→SERIES | |
| USER_ID | varchar FK→USER | |
| READ_COUNT | int | Completed books |
| IN_PROGRESS_COUNT | int | Started but not completed |
| READ_DATE | datetime NULL | Added V20240906 |
| PK | (SERIES_ID, USER_ID) | |

---

## Kobo Sync Tables

### SYNC_POINT
Source: `V20240529120934__syncpoint.sql`

| Column | Type | |
|---|---|---|
| ID | varchar PK | |
| CREATED_DATE | datetime | |
| USER_ID | varchar FK→USER | |
| API_KEY_ID | varchar NULL | |

### SYNC_POINT_BOOK
| Column | Type | Notes |
|---|---|---|
| SYNC_POINT_ID | varchar FK→SYNC_POINT | |
| BOOK_ID | varchar | |
| BOOK_CREATED_DATE | datetime | Snapshot at sync point creation |
| BOOK_LAST_MODIFIED_DATE | datetime | |
| BOOK_FILE_LAST_MODIFIED | datetime | |
| BOOK_FILE_SIZE | int8 | |
| BOOK_FILE_HASH | varchar | |
| BOOK_METADATA_LAST_MODIFIED_DATE | datetime | |
| BOOK_READ_PROGRESS_LAST_MODIFIED_DATE | datetime NULL | |
| SYNCED | boolean | |
| PK | (SYNC_POINT_ID, BOOK_ID) | |

---

## Ancillary Tables

### SIDECAR
Source: `V20210609165742__sidecars.sql`

| Column | Type | Notes |
|---|---|---|
| URL | varchar PK | Sidecar file path |
| PARENT_URL | varchar | Parent book or series path |
| LAST_MODIFIED_TIME | datetime | |
| LIBRARY_ID | varchar | |
| TYPE | varchar | Added later (ARTWORK/METADATA) |
| SOURCE | varchar | Added later (SERIES/BOOK) |

### HISTORICAL_EVENT
Source: `V20220218111455__historical_events.sql`

| Column | Type | |
|---|---|---|
| ID | varchar PK | |
| TYPE | varchar | |
| BOOK_ID | varchar NULL | |
| SERIES_ID | varchar NULL | |
| TIMESTAMP | datetime | |

### AUTHENTICATION_ACTIVITY
Source: `V20210625155626__authentication_activity.sql`

Tracks login events (success/failure), including source, user-agent, IP, API key.

### SERVER_SETTINGS
Source: `V20230922143307__server_settings.sql`

Key-value store: `DELETE_EMPTY_COLLECTIONS`, `DELETE_EMPTY_READLISTS`, `REMEMBER_ME_KEY`, `REMEMBER_ME_DURATION`, `THUMBNAIL_SIZE`, task pool size, etc.

### CLIENT_SETTINGS_GLOBAL / CLIENT_SETTINGS_USER
Source: `V20250205151235__client_settings.sql`

Frontend configuration key-value store. Global settings can have an `ALLOW_UNAUTHORIZED` flag (for anonymous access to certain UI config).

---

## Task Queue DB (`tasks.sqlite`)

### TASK
Source: `komga/src/flyway/resources/tasks/migration/sqlite/V20231013114850__tasks.sql`

| Column | Type | Notes |
|---|---|---|
| ID | varchar PK | `Task.uniqueId` |
| PRIORITY | int | 0 (lowest) to 8 (highest) |
| GROUP_ID | varchar NULL | Serialization group (e.g. seriesId) |
| CLASS | varchar | Kotlin class name |
| SIMPLE_TYPE | varchar | Human-readable type name |
| PAYLOAD | varchar | JSON-serialized task parameters |
| OWNER | varchar NULL | Thread that claimed the task |
| CREATED_DATE | datetime | |
| LAST_MODIFIED_DATE | datetime | |
