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
/library/manga/<Title>/Vol.01/Ch.1.cbz # completed archive
```

For converted imports under the storage root `/library`:

```text
/library/imports/temp/upload-<job>/   # uploaded source archives
/library/imports/temp/import-<job>/   # conversion workspace
/library/imports/<series-id>/<book-key>.cbz
```

MangaDex IDs remain provider identifiers in the database. Fresh downloads choose a
sanitized title folder, with an internal ID suffix on collision. Existing populated
UUID folders are reused to avoid silently moving files. Scans index local originals
in place. Transcoded imports use internal Lychee series IDs and source-derived book
keys; these are not MangaDex identifiers. This change does not migrate existing
folders or rewrite scanned originals.
