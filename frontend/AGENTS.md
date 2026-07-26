# frontend/ — lychee webapp

Vue 3 SPA for lychee, a self-hosted manga/comic/ebook media server. See the
[repo-root AGENTS.md](../AGENTS.md) for the monorepo overview; this file covers
`frontend/` specifically.

## Stack

- **Framework:** Vue 3.5, Composition API, `<script setup lang="ts">` everywhere —
  no Options API, no runtime `defineComponent` prop declarations (use
  `defineProps<{...}>()` + `withDefaults`).
- **Language:** TypeScript, `strict: true`, `noUnusedLocals`/`noUnusedParameters`
  on (see `tsconfig.json`) — unused symbols are a build error, not a lint warning.
- **Build/dev:** Vite 7, package manager/runner is **Bun** (not npm/yarn/pnpm —
  `bun install`, `bun run <script>`, `bunx`).
- **Styling:** Tailwind CSS v4 (CSS-first config, no `tailwind.config.js` — see
  `src/style.css`) + DaisyUI 5.
- **State:** Pinia (setup-store syntax — `defineStore(id, () => {...})`, not the
  options-object form).
- **Routing:** Vue Router.
- **API client:** `openapi-fetch`, typed from a generated OpenAPI schema.
- **Testing:** Vitest + `@vue/test-utils`, `happy-dom` environment.
- **No ESLint/Prettier configured yet.** The repo's `PostToolUse` formatter hook
  is a no-op until `frontend/node_modules/.bin/{eslint,prettier}` exist — don't
  assume either runs. Match surrounding code style by hand; `vue-tsc` is the only
  automated gate today.
- **No path aliases** — imports are relative (`../types`, `./client`), not `@/…`.

## Layout

```
src/
  api/         # typed backend client + generated schema + SSE + read-query mappers
  components/  # reusable UI pieces (PascalCase .vue)
  layouts/     # AppShell (the persistent nav/chrome around routed views)
  views/       # one component per route; views/settings/ for the Settings sub-panels
  stores/      # Pinia stores
  lib/         # framework-free helpers (formatting, sorting, theme registry, toasts…)
  router/      # route table
  types/       # hand-authored UI-facing domain types
```

Routing (`router/index.ts`): most routes nest under `AppShell` (the persistent
chrome); the reader (`/read/:id`) is deliberately **outside** the shell — it's
full-screen and owns its own layout.

## The API layer — read this before touching data fetching

`src/api/schema.d.ts` is **generated, not hand-edited** — it's
`openapi-typescript` run against `backend/openapi.json`. After any backend
router/schema change:

```sh
# from repo root
just api-gen
# equivalent, run separately:
#   (backend)  uv run python scripts/dump_openapi.py
#   (frontend) bun run api:gen
```

Do this in the same change as the API-affecting edit — `bun run build` runs
`vue-tsc --noEmit` first and will fail on drift between the client and the
schema.

Three layers, don't collapse them:
- **`api/client.ts`** — the raw typed client (`export const api =
  createClient<paths>()`) plus narrowed type aliases pulled from
  `components["schemas"]`. Requests are same-origin; Vite's dev server proxies
  `/api` → `http://127.0.0.1:8000` (see `vite.config.ts`).
- **`api/queries.ts`** — functions that call `api.GET/POST/…` and map the raw
  API response shape to the UI-facing types in `types/`. This is also where API
  error bodies (`{"error": {"code", "message"}}` — see backend `AGENTS.md`) get
  turned into thrown `Error`s components can catch.
- **`types/index.ts`** — hand-authored UI domain types. Some still predate the
  generated client (a comment there says as much); prefer deriving new types
  from the generated `schema.d.ts` over hand-writing new duplicates.

**Live updates** go over SSE, not polling: `api/events.ts` owns one shared
`EventSource` (`connectTaskStream()`, called once at app start) and exposes
`activeTasks`, `onTaskDone`, `onTaskEvent` for views to react to scan/download
progress without each opening their own connection.

## Styling conventions

- **Use DaisyUI component classes and canonical Tailwind utilities** (`shrink-0`,
  `grow`) — not deprecated aliases (`flex-shrink-0`) and not raw arbitrary
  values (`aspect-[2/3]`, hex colors in `class=`) unless there's genuinely no
  token for it. If you need a repeated one-off value, add a named utility/class
  in `src/style.css` (see `.cover`, `.segmented`, `surface-border` there) rather
  than sprinkling the same arbitrary value across templates.
- Theming is a full DaisyUI theme swap (`data-theme` on `<html>`), not per-component
  dark-mode classes — themes are defined in `style.css` (`@plugin "daisyui/theme"`
  blocks) and registered in `lib/theme.ts`. Every theme has a light/dark
  "pair"; if you add a theme, add its pair too.
- Shared design tokens (border color, corner radius) live as CSS custom
  properties at the top of `style.css` (`--surface-border`, `--radius-*`) —
  reuse them instead of hardcoding a new border/radius value.
- Tailwind's class scanner purges classes it can't see in templates; if a class
  is only ever assembled from a TS string map (status colors, badge variants),
  it must be force-included via `@source inline(...)` in `style.css` (see the
  existing examples) or it will silently vanish from the production build.

## Commands

Run from `frontend/` (or via the root `justfile`):

```sh
bun install                 # install deps
bun run dev --port 5173     # dev server (proxies /api → :8000)
bun run typecheck           # vue-tsc --noEmit
bun run test                # vitest run
bun run build               # vue-tsc --noEmit && vite build (typecheck is part of build)
bun run preview             # serve the production build
bun run api:gen             # regenerate src/api/schema.d.ts from ../backend/openapi.json
```

**Full CI gate** (`just fe-check`): `bun run typecheck && bun run test && bun
run build`. Run this — or at least `typecheck` + `test` — before considering
frontend work done. A `Stop` hook already blocks on outstanding `vue-tsc`
errors, but tests are not hooked, so run them explicitly. For UI-visible
changes, also start `bun run dev` and check the change in a browser — type
checks and unit tests don't verify visual/interaction correctness.

## Testing

- Test files are colocated `*.test.ts` next to what they test (e.g.
  `components/ErrorState.test.ts`, `api/queries.test.ts`, `lib/description.test.ts`),
  picked up by Vitest's `include: ["src/**/*.test.ts"]`.
  There is no separate `__tests__/` tree.
- Component tests use `@vue/test-utils`'s `mount()` and assert on rendered
  text/emitted events, not internals — see `components/ErrorState.test.ts`.
- `happy-dom` is the test DOM environment (not `jsdom`).

## Component conventions

- Props: `defineProps<{...}>()` with `withDefaults` for defaults, not runtime
  prop objects. Document non-obvious props with a `/** ... */` comment above
  the field (see `CoverImage.vue`).
- Prefer composables/plain functions in `lib/` over component-to-component
  coupling for cross-cutting concerns (toasts: `lib/toast.ts`, theme:
  `lib/theme.ts`, sorting/formatting: `lib/sort.ts`/`lib/description.ts`).
- Route transitions, shimmer/skeleton states, and other "polish" details are
  usually already solved somewhere in `style.css` or an existing component —
  check before adding a new one-off animation.

## Architecture reference

Design rationale for the frontend stack choice is
[ADR 03](../notes/decisions/03-frontend-stack.md); the reader's requirements
(paging, prefetch, fit modes, progress tracking) are covered in
[ADR 11](../notes/decisions/11-reading-progress.md) and
[ADR 09](../notes/decisions/09-image-serving.md) (image/page serving the
reader consumes). The full ADR index is
[`../notes/decisions/`](../notes/decisions/).
