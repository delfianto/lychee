# Description rendering and corpus harness

Descriptions remain source Markdown in SQLite and the API. Rendering never edits,
locks, syncs, or regenerates metadata. `frontend/src/lib/description.ts` uses
markdown-it for prose, lists, headings, references, code, and ordinary GFM tables.
Raw HTML is disabled; links accept HTTP(S)/mailto, and Markdown image banners become
links instead of remote image embeds.

Two-column tables whose second heading is **Tags** are presented as structured
metadata. The first heading can be Namespace, blank, or any source label such as
Book 1, Part 2, or Volume A. Formatting in headings is interpreted by the Markdown
parser. Each table keeps its own scope; consecutive pasted tables are separated
when their header/alignment rows repeat. Prose before, between, and after tables
is preserved, including notes with no separating blank line. General tables stay
in the synopsis and scroll inside their own frame on small screens.

MangaDex anthology `|| … ||` blocks become native expandable spoiler sections,
including Volume labels. Tables inside a spoiler stay inside it; card text omits
spoiler contents.

Tag-only descriptions preview their book/part labels and open the existing full
description dialog. Plain-text cards strip Markdown and omit tag dumps. Incomplete
or unrecognized structures remain visible rather than being discarded.

## Sweep a real library

Use a new output filename for each export. The exporter opens SQLite in read-only
mode and refuses to overwrite an existing file; it does not start the application
or contact a metadata provider.

```sh
just description-export /path/to/lychee.db /tmp/descriptions.json
just description-audit /tmp/descriptions.json
```

The audit uses the production parser and exits nonzero when a record needs review.
It inventories scoped tags, generic tables, lists, and headings, checks link/embed
output, and reports IDs/titles for unresolved tag-table syntax. An optional report
file can be written with `bun run descriptions:audit /tmp/descriptions.json
/tmp/report.json` from `frontend/`.

For visual review, start `just fe-dev` and open
`http://localhost:5173/description-lab.html`. The lab includes 24 neutral structural
fixtures adapted from actual library variations. Open the exported JSON to browse
all descriptions, filter review candidates, compare source/full/detail/card
rendering, and try edits. Edits stay in the tab and are never saved to the library.
The lab is a development entrypoint; the production build ships the regular app.

Fixtures live in `frontend/fixtures/descriptions.json` and are exercised by unit
and component tests. Full library exports stay local and are not committed or
bundled. Add a minimal structural fixture when the sweep discovers a new case,
then rerun the corpus audit and the desktop/mobile preview.

## Initial live-library sweep (2026-10-24)

All 1,480 series were inspected: 981 nonempty descriptions, 980 unique. The new
renderer found 133 tag-bearing descriptions and 138 scoped tag sections, plus one
general four-column chapter comparison table and 14 anthology spoiler sections. No unresolved tag-table warnings or
unsafe render output remained. Book/Part headings, bold headings, blank namespace
headings, repeated sections, list formatting, autolinks, literal angle brackets,
and image banners are represented in the regression corpus. The original source
text, series IDs, and metadata locks are unchanged.
