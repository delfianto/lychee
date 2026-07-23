# Overview 3 — File Management & Sync

Keeping the database consistent with files on disk: identity, change detection, moves/renames, orphans.
Per-project detail: [komga](komga/README.md) · [kamiyomu](kamiyomu/README.md) · [mango](mango/README.md) · [lanraragi](lanraragi/README.md).

## Comparison

| Aspect | Komga | KamiYomu | Mango | LANraragi |
|---|---|---|---|---|
| Discovery | `Files.walkFileTree` (follow links) | n/a — app creates files | `Dir.entries` recursive scan | `File::Find` recursive (Shinobu) |
| Trigger | periodic (`ScanInterval` per library) + on-startup + manual | daily re-crawl + `File.Exists` check | fiber loop every N min (default 5) | **filesystem watcher** (inotify, 1 s poll) + startup scan |
| File watcher | **none** (deliberate — NFS/SMB unreliable) | none | none | **Shinobu** (`File::ChangeNotify`) |
| File identity | `fileHash` = **XXH3-128 (full file)** + `fileSize` | none (owns the files) | **inode** number (+ dir signatures) | **SHA-1 of first 512 KB** (content ID) |
| Change detection | dir/file `max(ctime,mtime)` → then size+hash to confirm | `File.Exists` per expected chapter | `contents_signature` = SHA-1 of sorted filenames (structure only) | content hash changes; Shinobu path diffing |
| Move/rename restore | match new file to soft-deleted by **size then hash**; migrate media, thumbs, **progress**, readlist, collections | — (re-download) | **3-step lookup**: path+sig → path → sig+path-similarity | ID stable if content unchanged; update `file`/`name` fields; `change_archive_id` on collision |
| Orphan handling | **soft delete** (`deletedDate`) + "empty trash" task | leaves CBZ on disk when Library removed | `unavailable=1` flag, kept, admin can purge | `clean_database` (auto-backup first) removes missing |
| Dedup | page-hash dedup table (find/delete duplicate pages) | none | none | same-ID archives collapse (`change_archive_id`); cover Hamming-distance dupes | 
| Concurrency | task group-id serialization; `@Transactional` writes | Hangfire jobs | **all DB via one fiber** (ARM workaround) | per-archive Redis write-lock (`archive-write:<id>`) |
| Extra caches | — | MonkeyCache (TTL) | gzipped-YAML library snapshot + LRU | CHI FastMmap page cache; search cache |

## Patterns & divergences

- **Polling vs watching is a genuine split with a documented reason.** Komga *deliberately* avoids OS file-watching: its code comments call out **NFS/SMB cache unreliability** (directory mtime not updating when a contained file changes) — hence the `scanForceModifiedTime` option that recomputes a directory's effective mtime as `max(dir_mtime, max(child_mtimes))`. LANraragi *does* watch (Shinobu/`File::ChangeNotify`, inotify on Linux, polling on Windows). Mango and KamiYomu poll / re-crawl.
  → The robust answer is **both**: a watcher for low-latency pickup on local disks, and a periodic full scan as the correctness backstop (and the only reliable option on network mounts).
- **File identity is the hardest problem and everyone solved it differently:**
  - **Komga** — surrogate id; on scan, match by URL, and to survive *moves*, match a new file to a soft-deleted record by **file size then full-file XXH3-128**. Robust; costs a full-file hash.
  - **Mango** — **inode** as the "signature", with a brilliant **3-step fallback** (`path+signature` → `path-only` → `signature-only + path-component similarity`) that preserves progress across renames, moves, and edits. But inodes are **not stable** across remounts / filesystem migrations.
  - **LANraragi** — the id *is* content (SHA-1 of first 512 KB); stable across renames for free, but **false collisions** when files share a header, and change-detection misses edits after the first 512 KB.
  - **KamiYomu** — sidesteps it entirely by owning the files.
- **Soft-delete is the key to not losing user data.** Komga never hard-deletes on disk-removal — it sets `deletedDate`, which is what makes move/rename *restore* (and thus progress preservation) possible; a separate "empty trash" step purges. Mango's `unavailable=1` is the same idea. This is essential: users reorganize libraries and expect progress to survive.
- **Structure-only vs content change detection.** Mango's `contents_signature` (SHA-1 of sorted filenames) catches add/remove/rename but **not content edits**; LANraragi's 512 KB hash catches early-byte edits but not late ones. Komga's size+full-hash catches everything but is the most expensive. Combine mtime (cheap first gate) with size + a hash (confirm).

## Recommendation for lychee

- **Identity:** surrogate primary key **plus** a stored `(file_size, partial_hash, full_hash?)` for restore-on-move. Use a fast partial hash (e.g. XXH3 of head+tail+size) as the cheap signal; compute a full hash lazily only when confirming a move or on demand. **Avoid inode-only** (unstable) and **avoid a content-hash primary key** (collisions, couples id to bytes). This blends Komga (size+hash restore) with Mango's fallback ladder.
- **Change detection ladder:** `mtime`/size changed? → re-hash to confirm real content change → only then re-analyze. Add Komga's `force_modified_time` (recompute dir mtime from children) for NFS/SMB.
- **Sync triggers (both):** a `watchfiles`/`watchdog` watcher for local-disk latency **and** a scheduled full scan per library (configurable interval, plus on-startup and manual) as the backstop. Debounce watcher events (files land in bursts; LANraragi waits for the file to be openable and to reach a stable size before hashing).
- **Soft-delete + trash:** mark missing rows `deleted_at` instead of deleting; a restore pass matches new files to deleted rows by `(size, partial_hash)` and migrates **media, thumbnails, reading progress, tags, collection/readlist membership** (Komga's exact set); a retention/"empty trash" job purges after N days.
- **Concurrency:** run scans in the task queue with **per-series serialization** (Komga group-id) so two scans of the same series can't interleave. Wrap reconciliation writes in transactions. Enable SQLite WAL; keep the writer single (queue-serialized) to avoid `SQLITE_BUSY`.
- **Ingestion hardening (from LANraragi):** wait until a new file is openable and size-stable before importing; take a per-book lock during import; write an auto-backup before any bulk deletion.
