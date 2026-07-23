# LANraragi Redis Key Schema

Redis is the **sole** persistent datastore. Five logical databases are used (configured in `lrr.conf`):

| DB # | Purpose | Default |
|------|---------|---------|
| 0 | Archive hashes + tag indexes | `redis_database` |
| 1 | Minion job queue | `redis_database_minion` |
| 2 | Application config | `redis_database_config` |
| 3 | Search indexes + cache | `redis_database_search` |
| 4 | Metrics | `redis_database_metrics` |

Sources: `lib/LANraragi/Model/Config.pm` lines 37-49; `lrr.conf`.

---

## Database 0 — Archives

### Archive hash: `<sha1_40char_hex>`

One Redis HASH per archive. The key is the SHA-1 hex digest of the first 512 KB of the file (see `lib/LANraragi/Utils/Database.pm` `compute_id`, line 592).

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Filename without extension (redis_encoded UTF-8) |
| `title` | string | Display title (set by user or plugin; defaults to `name`) |
| `tags` | string | Comma-separated tag list, e.g. `artist:foo, parody:bar, date_added:1700000000` |
| `summary` | string | Optional long description |
| `file` | string | Absolute filesystem path to the archive (not encoded) |
| `isnew` | string | `"true"` or `"false"` — new-since-scan flag |
| `progress` | integer | Last-read page number (0 = unread) |
| `pagecount` | integer | Total number of pages/images |
| `lastreadtime` | integer | Unix timestamp of last progress update |
| `arcsize` | integer | File size in bytes |
| `toc` | JSON string | `{"<page_0based>": "<chapter_name>", ...}` — optional chapter markers |
| `thumbhash` | string | SHA-1 hex of first cover-page image bytes (used for duplicate detection) |
| `thumbjob` | integer | Minion job ID of a pending page-thumbnail generation job |
| `stamps` | JSON string | Array of stamp key names `["STAMPS_<page>_<ts>", ...]` |

Source: `lib/LANraragi/Utils/Database.pm` `build_json` (line 234), `add_archive_to_redis` (line 39).

---

### Stamp hash: `STAMPS_<page>_<unix_ms>`

One Redis HASH per annotation (a user-drawn callout/bookmark on a specific page).

| Field | Description |
|-------|-------------|
| `content` | Text content of the stamp |
| `position` | JSON string with x/y coordinates |
| `archive_id` | Back-reference to the parent archive key |

Source: `lib/LANraragi/Model/Stamp.pm` `add_stamp` (line 122).

---

### Category hash: `SET_<unix_timestamp_10digits>`

One Redis HASH per category. Key pattern matched by `SET_??????????` (14 chars).

| Field | Description |
|-------|-------------|
| `name` | Display name (redis_encoded) |
| `search` | If non-empty, this is a **dynamic** category: value is a search predicate string |
| `archives` | JSON array of archive IDs — only populated for **static** categories |
| `pinned` | `1` or `0` — show at top of category list |

Source: `lib/LANraragi/Model/Category.pm` `create_category` (line 121), `get_category` (line 73).

---

### Tankoubon sorted set: `TANK_<unix_timestamp_10digits>`

One Redis ZSET per tankoubon. Key pattern matched by `TANK_??????????` (15 chars).

Score-to-member encoding (negative scores are reserved for metadata):

| Score | Member format | Meaning |
|-------|--------------|---------|
| `0` | `name_<encoded_name>` | Tankoubon display name |
| `-1` | `summary_<encoded_summary>` | Optional summary text |
| `-2` | `tags_<encoded_tagstring>` | Tankoubon's own comma-separated tags |
| `-3` | `progress_<page>` | Last-read global page number across all archives |
| `1, 2, 3, ...` | `<archive_id>` | Member archives in reading order |

Fetching metadata uses `ZRANGEBYSCORE TANK_xxx -3 0`; fetching archives uses `ZRANGEBYSCORE TANK_xxx 1 +inf`.

Source: `lib/LANraragi/Model/Tankoubon.pm` `create_tankoubon` (line 71), `fetch_metadata_fields` (line 602).

---

## Database 2 — Config

### Config hash: `LRR_CONFIG`

All application settings are fields of this single HASH. Key examples: `dirname`, `thumbdir`, `password`, `apikey`, `pagesize`, `enablepass`, `tagrules`, `usedateadded`, `jxlthumbpages`, etc.

Source: `lib/LANraragi/Model/Config.pm` `get_redis_conf` (line 108).

### Filemap hash: `LRR_FILEMAP`

Maps absolute filesystem paths to archive IDs (maintained by Shinobu).

```
LRR_FILEMAP  (hash)
  "/path/to/archive.zip"  =>  "<sha1_hex>"
  ...
```

Source: `lib/Shinobu.pm` `update_filemap` (line 127), `add_to_filemap` (line 185).

### Tag rules list: `LRR_TAGRULES`

Redis LIST of flattened tag-rule triplets `[match, value, type, match, value, type, ...]` (3 elements per rule, stored via `lpush` so `lrange 0 -1` gives them reversed).

Source: `lib/LANraragi/Utils/Database.pm` `save_computed_tagrules` / `get_computed_tagrules` (line 627).

### Statistics scalar: `LRR_TOTALPAGESTAT`

Running integer count of total pages read across all sessions (incremented by `INCR` on each progress update).

Source: `lib/LANraragi/Controller/Api/Archive.pm` `update_progress` (line 486).

---

## Database 3 — Search Index

### Title sorted set: `LRR_TITLES`

Lexicographically sorted set; score is always 0; members are `"<lowercase_title>\x00<id>"`. Used for title search (`ZSCAN` with glob patterns) and title-sorted listing.

Source: `lib/LANraragi/Utils/Database.pm` `set_title` (line 428); `lib/LANraragi/Model/Stats.pm` `build_stat_hashes`.

### Tag index sets: `INDEX_<encoded_tag>`

One Redis SET per unique tag (lowercased, redis_encoded). Members are archive IDs (or tankoubon IDs). Example: `INDEX_artist:foobar` contains all archive/tank IDs tagged with `artist:foobar`.

Source: `lib/LANraragi/Utils/Database.pm` `update_indexes` (line 530).

### Tag statistics sorted set: `LRR_STATS`

Sorted set where each member is a lowercased, encoded tag and score is its occurrence count. Used to build the tag cloud. Scores are incremented/decremented as tags are added/removed.

Source: `lib/LANraragi/Utils/Database.pm` `update_indexes` (line 554).

### New archives set: `LRR_NEW`

Set of archive IDs where `isnew = "true"`.

### Untagged archives set: `LRR_UNTAGGED`

Set of archive IDs that have no "meaningful" tags (tags in namespaces `artist`, `parody`, `series`, `language`, `event`, `group`, `date_added`, `timestamp`, `source` do **not** count as meaningful).

Source: `lib/LANraragi/Utils/Database.pm` `update_indexes` (line 577).

### Tank-grouped set: `LRR_TANKGROUPED`

Set of IDs visible in a "group tanks" search: contains all tankoubon IDs plus all archive IDs that are **not** in any tankoubon. Archives absorbed into a tank are removed from this set.

Source: `lib/LANraragi/Model/Tankoubon.pm` `update_archive_list`; `lib/LANraragi/Utils/Database.pm` `add_archive_to_redis` (line 65).

### URL map hash: `LRR_URLMAP`

Maps normalized source URLs to archive IDs (populated from `source:` tags). Used to prevent duplicate downloads.

Source: `lib/LANraragi/Model/Stats.pm` `build_stat_hashes`.

### Search cache hash: `LRR_SEARCHCACHE`

Each field key is a redis_encoded cache key (composed of `category-filter-sortkey-sortorder-newonly-untaggedonly-grouptanks-hidecompleted`). The field value is a Perl `Storable`-frozen array of IDs. Cache is busted (`DEL` + recreate with `created` timestamp) on any metadata change.

Source: `lib/LANraragi/Model/Search.pm` `do_search` (line 64); `lib/LANraragi/Utils/Database.pm` `invalidate_cache` (line 615).

### Duplicate groups hash: `LRR_DUPLICATE_GROUPS`

Written by the `find_duplicates` Minion task. Field keys are `dupgp_<composite>`, values are JSON arrays of duplicate archive IDs.

Source: `lib/LANraragi/Utils/Minion.pm` `find_duplicates` (line 279).

### Initialisation marker: `LAST_JOB_TIME`

Unix timestamp set by `build_stat_hashes`. The search engine checks for its existence; if absent, returns `-1` with a "not initialized" warning.

Source: `lib/LANraragi/Model/Search.pm` `do_search` (line 33); `lib/LANraragi/Model/Stats.pm` (line 135).
