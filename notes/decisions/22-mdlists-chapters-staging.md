# 22 — MDLists, chapter availability, and fixed ingest staging

**Status:** Implemented; extends ADRs 05, 13, 16, and 19.

## MDLists

Collections carry MangaDex IDs, owner IDs, visibility, upstream versions, owned and
followed flags, and the last successful sync time. Existing provider-linked rows
start read-only until sync establishes their capabilities. Owned and followed
lists come from separate paginated MangaDex endpoints. Any public list can also
be imported by URL/UUID, and public lists can be discovered by user URL/UUID.

Owner edits write to MangaDex before changing local state. Every write checks the
current authenticated account against the live list owner. Renames and visibility
changes use the latest upstream version; membership uses dedicated add/remove
endpoints, so it cannot replace unrelated members from a stale snapshot. A list
creation is not automatically retried because the API has no idempotency key.
Provider failures become actionable domain errors, and leave the local edit unapplied.

A process-wide list lock covers snapshot reconciliation and user writes. The
long account metadata import fetches fresh list snapshots before reconciliation.
Incomplete metadata does not erase a list's previous complete membership.
Unfollowing/deleting upstream does not delete manga or downloaded files.

`DELETE /collections/{id}` removes the local collection. Remote deletion requires
`remote=true`, live ownership, and an explicit UI confirmation. Local descriptions
remain local because MangaDex lists expose names and visibility, not descriptions.

List imports and refreshes run on the existing task queue (`mdlist` tasks). Feed
requests paginate `/list/{id}/feed`, use the preferred or explicitly selected
language, include all supported content ratings, and exclude future/unavailable
chapters. Feed items link to series details and MangaDex chapter pages.

## Chapter availability

A readable chapter can have `chapter: null` (usually a oneshot). Such rows use the
label `Oneshot` and retain provider IDs for identity, file-name disambiguation,
download planning, and local/remote merge. They are not deduplicated by that label.

A successful nonempty preferred-language feed is the common fast path. An empty
feed triggers a cross-language diagnostic including unavailable and external
records. Its result distinguishes no chapters, other readable languages,
unavailable records, and external-only chapters. An inconsistent or failed check
is an error, never evidence of an empty manga. No legal-removal reason is inferred.

The cached snapshot includes the selected language and check time. Changing
language refreshes the index. Failed requests leave existing chapters intact and
have a 60-second cooldown; the retry control bypasses it. Old index rows without
a snapshot are refreshed, repairing previously cached false-empty results.

## Storage

`temp/` is reserved under the destination library root; it is not configurable.
Downloads stage original pages, encode AVIF, and pack a CBZ in a per-job directory
there. Completed archives move into the catalog tree with a same-filesystem atomic
rename. The encoder consumes page files incrementally; the process pool bounds
pending work. Import conversion follows the same publication rule. Temporary
workspaces are cleaned on normal success, cancellation, and exceptions. A killed
process can leave an orphan workspace, which remains excluded from scans.

For a manga library rooted at `/library/manga`:

```text
/library/manga/temp/download-<job>/    # incomplete source pages + archive
/library/manga/<MangaDex UUID>/Vol.01/Ch.1.cbz # completed archive
/library/manga/<MangaDex UUID>/Ch.2.cbz        # volume unknown
/library/manga/<MangaDex UUID>/Oneshot [<chapter-id-prefix>].cbz # unnumbered, no volume
```

For converted imports under the storage root `/library`:

```text
/library/imports/temp/upload-<job>/   # uploaded source archives
/library/imports/temp/import-<job>/   # conversion workspace
/library/imports/<series-id>/<book-key>.cbz
```

MangaDex downloads use the MangaDex UUID as their series folder, independent of the
current title or previous `path_rel`. This keeps filesystem names deterministic
across metadata changes and fresh imports. The initial title-folder policy was
reverted in favor of stable provider identity. Existing title folders are not moved
or migrated; their contents must be cleared and downloaded again when resetting a
library. Scans index local originals in place. Transcoded imports use internal
Lychee series IDs and source-derived book keys; these are not MangaDex identifiers.

### Volume reconciliation

`downloads/paths.py` reconciles downloaded MangaDex chapters by provider chapter
UUID whenever the remote feed is refreshed (sync, chapter check, or download
planning). A null volume means the archive belongs directly under the series
folder; a numbered volume means `Vol.XX/`. Existing `No Volume/` archives are
flattened by the same pass. Volume corrections in either direction are supported;
absence from a feed does not change a local chapter. A oneshot follows an explicit
provider volume if one exists. Filenames stay unchanged during reorganization.

Only provider-owned, single-chapter CBZs in the managed layout are eligible.
Arbitrary scanned containers and shared multi-chapter books are never moved.
`Book.path_rel` and `Chapter.volume` change together while Book/Chapter IDs, reading
progress, and image caches remain intact. Neither downloads nor encoding nor
thumbnail generation is repeated. Scanning preserves the logical metadata of an
existing provider chapter, including its oneshot label.

Publication, reconciliation, and scans share the library's index lock, retained
through the database transaction. Downloads hold it only after encoding; they
re-read the current indexed volume before publishing. Queued/paused/failed rows
also receive updated volume metadata. File operations use the shared I/O budget.

Moves create a hard link to the existing CBZ without overwriting a destination.
Both paths remain readable until commit; commit removes the original, rollback
removes the new link. A flushed, atomically published journal under the hidden
`.lychee-moves/` directory records both paths and the archive's filesystem identity.
Startup recovers journals before resuming downloads; scans and later moves recover
them before indexing. Recovery follows the committed Book path and refuses to
delete a replaced file. Unresolved journals stop that operation rather than letting
a scan index duplicate aliases. The filesystem must support same-filesystem hard
links; failures leave the source archive intact and fail the sync for retry.
Empty old volume folders are removed. No database migration or API change is needed.

## Coordinated pipeline follow-up

Scans now retain ownership through cover and gallery thumbnail generation rather
than launching a detached thumbnail task. Downloads fetch MangaDex files
concurrently, overlap fetching with conversion, and stay active through thumbnail
work. Phase counters and cancellation follow the complete operation; see
[ADR 08](08-task-runner.md) for worker budgets and cancellation boundaries.
