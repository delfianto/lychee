# 03 — Frontend: Vue 3 + Tailwind + DaisyUI (SPA)

**Status:** Implemented.

## Stack

A decoupled Vue 3 SPA, fully API-driven (no server-rendered pages):

- **Framework:** Vue 3.5, Composition API, `<script setup lang="ts">`
  everywhere — no Options API, no runtime `defineComponent`.
- **Language:** TypeScript, `strict: true`, `noUnusedLocals`/
  `noUnusedParameters` on — unused symbols are a build error.
- **Styling:** Tailwind CSS v4 (CSS-first config, no `tailwind.config.js`) +
  DaisyUI 5.
- **State:** Pinia (setup-store syntax). **Routing:** Vue Router.
- **API client:** `openapi-fetch`, typed from `frontend/src/api/schema.d.ts`
  (generated from `backend/openapi.json` via `bun run api:gen`) — regenerated
  in the same change as any backend router/schema edit.
- **Build/tooling:** Vite 7, Bun as package manager/runner (not npm/yarn/pnpm).
- **Testing:** Vitest + `@vue/test-utils`, `happy-dom` environment, colocated
  `*.test.ts` files.
- **Realtime:** one shared `EventSource` (`api/events.ts`'s
  `connectTaskStream()`) consuming backend SSE for scan/download/task
  progress — no polling anywhere.
- **No path aliases** (relative imports only). **No ESLint/Prettier
  configured yet** — `vue-tsc` is the only automated gate; a `PostToolUse`
  formatter hook is a no-op until those bins exist.
- **Convention:** canonical Tailwind class forms (`shrink-0`, `grow`, not
  `flex-shrink-0`), DaisyUI component classes over raw arbitrary values.

## Layout

```
src/
  api/         typed client + generated schema + SSE + read-query mappers
  components/  reusable UI pieces (PascalCase .vue)
  layouts/     AppShell — the persistent nav/chrome around routed views
  views/       one component per route; views/settings/ for Settings sub-panels
  stores/      Pinia stores
  lib/         framework-free helpers (formatting, sorting, theme registry, toasts)
  router/      route table
  types/       hand-authored UI-facing domain types
```

The reader route (`/read/:id`) is deliberately **outside** `AppShell` —
full-screen, its own layout. It's a real, custom-built component: paging,
fit-to-width/height modes, keyboard navigation, and progress tracking on
scroll are all implemented (`views/ReaderView.vue`); page **prefetch** of
upcoming pages is not — pages load on demand.

## Mock harness

`bun run dev:mock` (or `just fe-mock`) serves the SPA against MSW instead of
a real backend — `src/mocks/handlers.ts` (one handler per real endpoint,
mutating endpoints edit in-memory fixtures for the session),
`src/mocks/data/*.ts` (hand-authored + seeded-random fixtures), `taskBus.ts`
(simulates the task queue's SSE lifecycle). Dev/demo tooling only, not wired
into `bun run test`.

## Why an SPA over server-rendered

A fully decoupled SPA makes the frontend "just another client" of the REST
API — the same relationship `mcp/` and any future third-party client would
have — at a cost (a second toolchain, a second app) the monorepo + generated
typed client largely absorbs (a build breaks on any API drift, so the
contract can't silently rot). The reader specifically needs to be a
rich-JS component regardless of the rest of the app's rendering strategy —
paging, fit modes, and keyboard nav all need real client-side state — so a
server-rendered shell around it would still need a JS reader bolted on,
without the "just another client" decoupling benefit.
