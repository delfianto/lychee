# 03 — Frontend: Vue 3 + Tailwind + DaisyUI (SPA)

**Status:** ✅ Accepted

## Context

The research ([01-stack](../01-stack.md)) framed the frontend's "real fork" as **SPA vs server-rendered**: an SPA gives the best reader UX and full decoupling (enabling future mobile/third-party clients), at the cost of maintaining a second app — a cost the **monorepo + generated API types** ([01](01-repo-structure-monorepo.md)) largely neutralizes. TBM uses a Vue 3 + Tailwind + DaisyUI SPA and it works well; we reuse that stack.

## Decision

A decoupled **Vue 3 SPA**, same stack as TBM:

- **Framework:** Vue 3.5 (Composition API) + TypeScript.
- **Styling/components:** Tailwind CSS v4 + **DaisyUI 5** (utility-first + component classes).
- **State / routing:** Pinia + Vue Router.
- **API client:** typed client generated from the backend's `openapi.json` (openapi-fetch / `bun run api:gen`) — regenerated on any API change.
- **Build/tooling:** Vite + Bun (TBM uses the VoidZero `vp`/Vite+ toolchain; standard Vite+Bun is the baseline).
- **Realtime:** consume backend SSE for scan/progress events.
- **Convention:** canonical Tailwind class forms (`shrink-0`, `grow`, not `flex-shrink-0`) — TBM rule.

**The reader is a first-class, rich-JS component.** Every reference project — even the server-rendered ones — drops to custom JS for the reader (Komga uses a Readium reader; Mango/LANraragi ship `reader.js`/Swiper). It needs paging, prefetch of the next N pages, fit-to-width/height, keyboard nav, and progress-on-scroll.

## Consequences

- Fully decoupled: the SPA is "just another client", so mobile apps / third-party clients remain possible.
- Typed API via codegen keeps the FE/BE contract honest (build breaks on drift).
- Cost — a JS toolchain and a second app — is mitigated by the monorepo, shared `justfile`, and shared `.claude` hooks.

## Alternatives considered (from research)

- **HTMX + server-rendered (KamiYomu):** much less JS, but the reader fights the model and you lose clean decoupling.
- **Server-rendered templates (Mango ECR / LANraragi TT2):** simplest, but dated UX and no first-class API-driven client.
- **Vuetify (what Komga uses, on Vue 2.6):** rejected in favor of the more modern, lighter Tailwind + DaisyUI on Vue 3.
