# Testing and coverage review — 2026-10-23

The backend already had substantial tests. The main gaps were the frontend and
MCP tools. Comparing with `../the-bannered-mare/frontend/TESTING.md` and its CI
showed that Lychee lacked whole-app coverage reporting, enforced thresholds,
retained CI reports, and coverage for most UI state and MCP orchestration.

## Measured results

| Surface | Tests before → after | Lines now | Branches now | Combined Python coverage |
| --- | ---: | ---: | ---: | ---: |
| Backend | 273 → 273 | 89.37% | 75.80% | 86.82% |
| Frontend | 58 → 210 | 98.40% | 92.66% | — |
| MCP | 6 → 25 | 100% | 100% | 100% |

Frontend coverage started at **13.78% lines, 13.19% branches, 13.59%
statements, and 12.21% functions**. The first expansion reached 34.54% lines
with 152 tests. After the second review it measures **98.40% lines, 92.66%
branches, 97.38% statements, and 96.72% functions** across 210 tests.
Unimported views remain in the denominator.
MCP's initial combined coverage was approximately 44%; its six tests exercised
only the client and models, leaving all tool orchestration unexecuted.

The backend suite mixes pure unit tests with API/service integration tests over
a temporary SQLite database. The frontend mixes pure helpers, reactive state,
real-client HTTP contract tests, mounted components, and routed reader/search
screens. MCP tools run through their real HTTP client against MockTransport.
These counts should not all be described as pure unit tests.

## Run and inspect

From the repository root, with dependencies installed:

```sh
just check           # format/lint/types + coverage gates on all three surfaces
just be-coverage
just fe-coverage
just mcp-coverage
```

For a focused frontend test, run `bun run test -- src/views/ReaderView.test.ts`
from `frontend/`. Plain pytest and `bun run test` remain available for quick
iterations; the `*-check` recipes and CI enforce coverage.

Frontend HTML starts at `frontend/coverage/index.html`; LCOV and JSON summaries
are alongside it. Python HTML starts at `backend/coverage/html/index.html` and
`mcp/coverage/html/index.html`, with XML and JSON under each `coverage/` folder.
CI retains separate frontend/backend/MCP report artifacts for seven days,
including reports produced by failing tests. Reports and coverage data files
are ignored by git. MCP now has its own CI job, triggered by MCP changes.

## Gates and comparison with TBM

Lychee now matches TBM's **85% minimum on all four frontend metrics**, plus
stricter critical-file floors. Both local `just fe-check` and frontend CI enforce
them. No product files were removed from coverage to reach the target. Raise
floors as meaningful tests grow; do not hide difficult files or replace product
behavior with stubs to increase the percentage.

Separate frontend floors prevent unrelated tests from masking core regressions:

| Area | Lines | Statements | Functions | Branches |
| --- | ---: | ---: | ---: | ---: |
| Each library helper | 95 | 85 | 95 | 65 |
| SSE task state | 100 | 100 | 100 | 100 |
| Read/query API layer | 95 | 95 | 95 | 90 |
| Settings API layer | 90 | 85 | 95 | 75 |
| Each store | 95 | 95 | 95 | 90 |
| Tested dialogs, path browser, cover image, each | 90 | 90 | 80 | 85 |
| Reader screen | 90 | 90 | 70 | 90 |
| Search screen | 95 | 95 | 95 | 90 |
| App shell | 100 | 100 | 100 | 90 |
| Series/gallery detail, each | 95 | 90 | 95 | 80 |
| Taxonomy/download/import settings, each | 95 | 95 | 95 | 85 |
| MangaDex/tracker auth dialogs, each | 95 | 95 | 90 | 85 |
| Accounts settings | 95 | 95 | 90 | 90 |
| Appearance settings | 85 | 80 | 80 | 85 |

Python gates use coverage.py's **combined statement/branch** percentage:
85% backend and 95% MCP. An 85% combined gate does not mean 85% branch coverage.
Backend development seed code remains included even though it is untested.

## Behaviors added

- API contracts use the real `openapi-fetch` client and test-owned MSW responses:
  nullable metadata, taxonomy grouping, filtered/cursor requests, gallery paging,
  download actions, provider/tracker credentials, filesystem conflicts, settings
  payloads, HTTP failures, and API error messages.
- Preferences cover shared reactivity, persisted values, clamping, debounced font
  writes, theme pairs, label-load retries, and toast expiry with fake timers.
- Components cover confirmation/prompt actions, disabled and blank submissions,
  reopening drafts, cover failures, path fallback, file/directory selection,
  directory-create failure and retry, and cleanup on unmount.
- Reader tests use a memory router and exercise local chapter order, RTL/LTR
  keys and click zones, progress writes, final-page navigation, display settings,
  and stale chapter responses. Search tests cover deep links and debounce races.
- Additional real-component workflows cover the actual application routes and
  navigation shell; library filters/presets and density; collection creation,
  renaming, and removal; metadata edits and provider matching; gallery preview
  fallbacks; settings toggles; scans; taxonomy names/aliases/pagination; bulk and
  individual downloads; import presets and multipart uploads; OAuth nonce
  callbacks; credentials files; and task-driven refresh/cleanup.
- Controlled intersection/resize signals cover pagination backpressure and rail
  scrolling. A fake only at the Plyr boundary checks player construction,
  autoplay rejection, auto-next, focus handling, and teardown. Pointer-event
  tests verify font-size dragging against frozen geometry while the UI rescales.
- MCP tests cover camelCase requests/results, all filter mappings, cursor
  exhaustion/result caps, tag union/subtraction/replacement, deduplication,
  per-item batch failures, input validation, scans, downloads, and taxonomy.

Search regressions reproduced before the fix: an older response overwrote newer
results, and a pending debounce fired after unmount. The view now invalidates
stale responses and clears its timer during teardown.

Further regression tests reproduced and fixed:

- Taxonomy inline editing called `.focus()` on the array Vue creates for refs
  inside `v-for`. The editor now focuses/selects the actual input.
- Editing a year crashed because Vue coerces number inputs before the form
  called `.trim()`. The form now normalizes its string/number input explicitly.
- The series PATCH wrapper ignored HTTP error responses, so rejected edits
  emitted success and closed the dialog. It now rejects errors; the form keeps
  the draft available for retry.
- Failed series/gallery preference writes restore displayed state and show an
  error. Per-field revisions keep an older rejection from overwriting a newer
  selection, including the tested overlapping-rating case.

## Test conventions and remaining gaps

Use assertions on visible state, public emits, routes, requests, and cleanup.
Use fake timers and controlled promises for delays and races. `src/test/setup.ts`
auto-unmounts Vue wrappers and clears DOM/storage; Vitest restores spies and
stubbed globals. Attach wrappers to the document when asserting focus/visibility.
MSW uses its v3 `onUnhandledFrame: 'error'` policy so unexpected requests fail.
The dev mock fixtures are not shared mutable test data.

Remaining risks are concentrated in semantics and integration rather than
unmounted screens. Collection optimistic writes and some settings mutations
still need rejected-write/rollback scenarios; their line coverage alone does
not prove correct error handling. Reader network failures and provider failures
also deserve further work. Backend library management, bootstrap, video probing,
and provider failure branches remain weaker than its aggregate coverage.

The shared setup auto-unmounts components and clears toasts, storage, and DOM so
failure-message assertions cannot pass because a previous test emitted the same
message. Each workflow gets fresh server-side fixture state. Unknown HTTP
requests fail the suite; failure cases are injected for specific methods/paths.

A one-off Chromium smoke check against Lychee's mock dev server also verified
real browser taxonomy focus/cancel and a numeric year save with no page errors.
It reused the adjacent TBM Playwright installation; no browser dependency was
added to Lychee.

TBM's persistent Playwright suite was not copied in this unit/coverage pass. DOM tests do
not establish real browser layout, native downloads/uploads, actual video
playback, service-worker behavior, or backend correctness behind mocked HTTP
responses. Those require separate browser/full-stack tests.
