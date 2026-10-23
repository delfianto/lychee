# Dependency review — 2026-10-23

Lychee now follows the frontend toolchain used by the adjacent Bannered Mare
project. The starting manifests already used Vite 8.3.1, Vitest 5.0.2, and
TypeScript 6.0.3; the Vite 7 references in the stack documentation were stale.

## TypeScript 7 and Vue

[TypeScript 7 is released](https://devblogs.microsoft.com/typescript/announcing-typescript-7-0/),
but its native compiler is not a direct replacement for the JavaScript compiler
API used by Vue's SFC tooling. Replacing `vue-tsc` with standalone `tsc`/`tsgo`
would lose Vue script/template checking.

Bannered Mare's frontend update (`6ba3a53`) uses
[`typescript-native-bridge`](https://github.com/johnsoncodehk/typescript-native-bridge).
Lychee adopts the same exact alias:

```json
"typescript": "npm:typescript-native-bridge@6.0.3-bridge.19.tsgo.7.0.2"
```

This community compatibility package retains the TypeScript 6.0.3 API while
running the TypeScript 7.0.2 native checker. It is a pinned prerelease bridge,
not stock TypeScript 7 support in Vue. `vue-tsc` prints `TNB ACTIVE` when loaded.
Its optional native packages cover glibc Linux, macOS, and Windows; Alpine/musl
is unsupported. Only Linux x64 was validated here. Keep the alias exact and
verify both ordinary TypeScript errors and Vue template errors when upgrading.

Vite+'s standalone type check is disabled because it misreads Vue SFC props.
The migrator's blanket `*.vue` declaration was removed; `vue-tsc` remains the
authoritative check. Type-aware Oxlint rules remain enabled.

## Vite+ and frontend dependencies

The official [Vite+ migration](https://viteplus.dev/guide/migrate) ran against
the existing lockfile with agent, editor, and hook installation disabled.
The project uses local `vite-plus@1.4.0`, which supplies Vite 8.3.5, Rolldown,
Vitest 5.0.5, Oxlint, and Oxfmt. Bun remains the package manager; no global `vp`
installation is needed for package scripts. Node 24 LTS is configured in CI;
Vite+ requires Node `^22.18.0 || ^24.11.0 || >=26.0.0`.

Keep `vite-plus`, the `vite` alias, and the `vite` override on the same exact
version. Import test APIs from `vite-plus/test` and configuration from
`vite-plus`. Unlike Bannered Mare, Lychee retains its separate Vitest config
so unit tests do not load Tailwind. No separate direct Vitest package is needed
for this project's current imports.

Vue, Router, Pinia, DaisyUI, MSW, Happy DOM, the Vue build/type-check tools,
flag icons, and Plyr were refreshed. Deprecated `lucide-vue-next` was replaced
with `@lucide/vue`. Bun is pinned to 1.4.4. The checked-in MSW worker was
regenerated from 3.0.3. Oxfmt's first pass accounts for most source-file changes;
generated API types and the MSW worker are excluded from formatting.

`just fe-check` and frontend CI now check formatting, lint, Vue types, tests,
and the production build. The existing frontend edit hook uses local Vite+.

## Python dependencies

Backend direct pins and both Python lockfiles were refreshed, including
FastAPI 0.161.1, SQLAlchemy 2.1.6, Alembic 1.20.1, Pydantic 2.14.1,
pydantic-settings 2.16.1, Pillow 13.0.0, FastMCP 4.1.3, Ruff 0.17.2,
and basedpyright 1.40.2. Python remains 3.14. CI uses published checkout,
setup-node, and setup-uv action releases and a locked backend install.

## Validation and remaining migrations

Counts below describe the dependency upgrade. The subsequent
[testing review](testing.md) records the expanded suites and coverage gates.

- Backend: format, lint, type checking, and all 273 tests passed, including
  AVIF/image, scan, API, and tracker coverage.
- MCP: format, lint, type checking, and all 6 tests passed.
- Frontend: frozen Bun install, format, lint, Vue type checking, all 58 tests,
  and production build passed.
- Temporary script and Vue template error probes failed with the expected
  TS2322 and TS2339 diagnostics while the native bridge was active; probes
  were removed afterward.
- Normal and mock dev servers served the entrypoint and transformed Vue
  components over HTTP. The mock worker was served successfully. These are
  HTTP smoke checks, not browser interaction tests.
- Migrations upgraded a temporary SQLite database and `alembic check` found
  no model drift. `just api-gen` produced no API contract changes.
- Plyr 3.8.5 is deprecated and receives security updates only. Replacing the
  gallery's player with Video.js 10 needs a separate component migration.
- Starlette's TestClient warns that its `httpx` transport is deprecated in
  favor of `httpx2`. Tests still pass; production provider clients retain
  their existing `httpx` API.
- Node type definitions remain on major 24 to match the chosen tooling runtime.
  No TypeScript speedup is claimed without a controlled benchmark.
