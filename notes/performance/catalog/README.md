# Catalog query optimization (2026-10-25)

This implements the follow-up to the [engine attribution study](../database/README.md).
SQLite remains the default. Local Turso remains optional; production is not switched
or redeployed by these changes.

## Implementation

Migration `a4b9d7e6c201` adds eight ordinary covering/order indexes, also declared
in ORM metadata so schema drift checks verify them:

- Series `(kind, created_at, id)`, `(kind, sort_title, id)`, `(kind, rating, id)`.
- Chapter `(series_id, provider_chapter_id, id, number_sort)`,
  `(series_id, created_at)`, `(series_id, source_uploaded_at)`.
- Provider chapter `(series_id, provider, published_at)`.
- Reading progress `(chapter_id, completed)`.

`catalog/series_stats.py` keeps two measured query shapes. SQLite retains indexed
correlated lookups and one SQL statement for page selection/hydration. A wholesale
grouped rewrite was slower on SQLite and was rejected. Native Turso selects a
bounded page and hydrates its display counts/dates using grouped statistics. For
sorts/filters that need a catalog-wide count/date, rollups compute them once per
series rather than repeating scalar subqueries in projection, filtering and order.
Narrow metadata filters scope these rollups; kind-only grids avoid a redundant
series traversal inside each rollup. Added/title ordering can stop early using
the order indexes, so their read filters retain indexed correlated predicates.

Native provider-read keys are deduplicated before joining. A chapter marked read
both locally and remotely, or through two provider records, still counts once.
Partial local progress still contributes last-read position. MangaDex chronology
continues to prefer the newest source publication/upload date, then local chapter
creation, then series creation. Other providers retain local chronology.

Native cursor boundaries come from selection, preserving continuation if a work
is removed/changed before hydration. Batched display IDs are deduplicated. Home
rails use the bounded fetch path too; no persisted summary/cache or invalidation
mechanism is introduced.

## Corrected checkpoint control

The earlier candidate-index experiment measured new native indexes before an
explicit checkpoint. A control found that this MVCC log state could turn a grouped
query from roughly 20ms into 140ms. Those measurements cannot by themselves prove a
persistent optimizer regression. Here both databases checkpoint after index builds
and reopen before optimized timing. Application startup now checkpoints local
Turso after migrations, before restoring background workers. A busy checkpoint
is logged; it does not invalidate the migration or silently overwrite data.

## Reproduce

```sh
just bench-catalog --temp-root /srv/project/github/lychee --output /tmp/catalog.json
just bench-catalog --reverse --temp-root /srv/project/github/lychee --output /tmp/catalog-reverse.json
just bench-catalog --catalog 10000 --iterations 3 --temp-root /srv/project/github/lychee --output /tmp/catalog-scale.json
just bench-catalog --operations-only --temp-root /srv/project/github/lychee --output /tmp/catalog-home.json
```

The full-operation harness loads historical query code from commit `9e35c2f` with
`git show` and executes it against disposable synthetic databases. It compares
old code/schema (new indexes absent) with new code/schema, not just the first SQL
statement. Each measured call opens a fresh Session and includes row hydration,
tags/credits, and cursor creation. Three warmups precede 30 timings per case.

`optimized-nvme-{1,2,3}.json` contain independent runs on the same btrfs/NVMe mount
as production appdata; round two reverses engine order. The fixture has 2,000
works, 4,000 local chapters, 40,000 provider chapters, local and remote progress,
varied dates/NULL ratings, manga/comic/gallery kinds, two libraries, authors and
tags. Twelve scenarios cover sorts, read state, library/favorites, authors/tags and
gallery/all-kind views. Every optimized first and continuation page must match
SQLite's historical reference, including counts, dates, tags and credits.

An old native `all-kinds` query fails with `AggStep: register 11 does not hold an
aggregate accumulator` on the richer fixture. The report records that baseline
error rather than inventing a speed comparison. The new query succeeds and
matches the SQLite reference. No real library data is stored in these artifacts.

## Repeated complete-operation results

Median of each run's p50, milliseconds. These are repository operation times,
not HTTP latencies; they are not comparable with the previous report's single-SQL
times. The host runs other services, so small differences remain indicative.

| Operation | SQLite before | SQLite after | Turso before | Turso after |
| --- | ---: | ---: | ---: | ---: |
| Recently added grid | 1.80 | 1.63 | 5.42 | 3.38 |
| Recently updated grid | 5.99 | 2.93 | 91.89 | 18.23 |
| Unread sort | 3.25 | 2.96 | 32.91 | 11.55 |
| Title sort | 1.78 | 1.60 | 5.08 | 3.37 |
| Rating sort | 1.85 | 1.84 | 5.34 | 3.77 |
| In-progress filter | 3.47 | 1.77 | 33.02 | 4.71 |
| Author + tags + updated | 2.91 | 2.57 | 104.51 | 46.08 |

SQLite's updated sort is about 2× faster; Turso's about 5×. Turso's unread sort
improves about 2.9× and its in-progress filter about 7×. Rating on SQLite is
essentially unchanged. Native Turso still has higher costs on these read workloads.

The supplemental home/batch run uses the original basic 2,000-work fixture, 30
samples per operation, with identical ordered outputs asserted before/after:

| Operation | SQLite before | SQLite after | Turso before | Turso after |
| --- | ---: | ---: | ---: | ---: |
| recently_added | 9.17 | 1.30 | 167.15 | 2.50 |
| continue_reading | 7.28 | 3.44 | 102.62 | 10.92 |
| batch24 | 1.24 | 1.15 | 4.14 | 2.59 |

These are one supplemental run, not three-run medians. The home added rail avoids
calculating display aggregates while sorting the entire catalog.

## Scale, space and write costs

`scale-10000-nvme.json` increases to 10,000 works/200,000 provider chapters (three
samples per case). SQLite's updated operation improves 23.00→8.16ms and Turso's
447.54→85.88ms. Turso's unread operation improves 145.65→43.93ms; its in-progress
filter improves 148.95→5.99ms. Publication sorting still needs a catalog-wide
rollup on native Turso, so this is not constant-time at arbitrary library size.

`storage-nvme.json` measures allocated pages, excluding freelist pages left when
removing indexes from the initial fixture. Plain file length misleadingly stays
unchanged as those free pages are reused. For 2,000 works, the eight indexes add
about 2.63MiB allocated on SQLite and 2.96MiB on Turso. At 10,000 works they add
about 13.15MiB / 14.95MiB respectively.

The three main runs also time 100 publication-date changes followed by rollback,
and a single progress toggle followed by rollback. Representative p50 costs are
0.035→0.068ms on SQLite and 0.258→1.390ms on Turso for the publication batch;
progress toggles remain about 0.012ms / 0.055ms. These measure transaction/index
maintenance, not commit durability or sustained write throughput. Updating the
indexed date has a real write cost; DownloadTask page-progress rows gain no index.

## Whole download regression check

`downloads-{sqlite,turso}-{1,2,3}.json` rerun the real AVIF/thumbnail/archive/API
harness. All runs finish all 30 chapters and all parent tasks; every API response
succeeds. Median throughput remains about 64.6 pages/s SQLite and 64.1 Turso.
The query improvements do not establish a download throughput improvement.
Aggregate API p95 is 16.7ms SQLite and 24.0ms Turso in these samples (previously
16.4/21.2ms); there is no demonstrated whole-application p95 improvement in this
small mostly-empty-catalog workload. The large gains above are from populated
library queries and home rails, not faster encoding.

## Validation and scope

- Backend formatting, lint, types and branch coverage gate pass: 424 tests pass,
  one native-only concurrency test skips on SQLite; coverage 89.72% (85% floor).
- Native suite: all 425 tests pass.
- Independent expected-value tests exercise all sorts/read filters, ties,
  two-item cursor pages, partial/local/duplicate-remote progress and publication
  fallback cases. A native test deletes between selection and hydration.
- Upgrade/downgrade preserve existing library/progress data on both engines;
  fresh migrations and Alembic drift checks pass on both.
- `just api-gen` produces no contract/client changes. No frontend change is needed.

Implementation and benchmark work are local to the current branch. No version
bump, push, production migration, image rebuild or container restart is included.
