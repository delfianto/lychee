import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite-plus";

export default defineConfig({
  plugins: [vue()],
  test: {
    environment: "happy-dom",
    environmentOptions: {
      happyDOM: {
        url: "http://localhost",
        settings: {
          navigation: { disableMainFrameNavigation: true, disableChildPageNavigation: true },
        },
      },
    },
    setupFiles: ["src/test/setup.ts"],
    restoreMocks: true,
    unstubGlobals: true,
    unstubEnvs: true,
    include: ["src/**/*.test.ts"],
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,vue}"],
      exclude: [
        "src/**/*.test.ts",
        "src/test/**",
        "src/mocks/**",
        "src/**/*.d.ts",
        "src/types/**",
        "src/main.ts",
      ],
      reporter: ["text-summary", "json-summary", "json", "html", "lcov"],
      reportOnFailure: true,
      thresholds: {
        // TBM's whole-app floor, including every unimported product screen.
        lines: 85,
        statements: 85,
        functions: 85,
        branches: 85,
        "src/lib/*.ts": {
          perFile: true,
          lines: 95,
          statements: 85,
          functions: 95,
          branches: 65,
        },
        "src/api/events.ts": { lines: 100, statements: 100, functions: 100, branches: 100 },
        "src/api/queries.ts": { lines: 95, statements: 95, functions: 95, branches: 90 },
        "src/api/settingsQueries.ts": { lines: 90, statements: 85, functions: 95, branches: 75 },
        "src/stores/*.ts": {
          perFile: true,
          lines: 95,
          statements: 95,
          functions: 95,
          branches: 90,
        },
        "src/components/{ConfirmDialog,PromptDialog,PathBrowserModal,CoverImage}.vue": {
          perFile: true,
          lines: 90,
          statements: 90,
          functions: 80,
          branches: 85,
        },
        "src/views/ReaderView.vue": { lines: 90, statements: 90, functions: 70, branches: 90 },
        "src/views/SearchView.vue": { lines: 95, statements: 95, functions: 95, branches: 90 },
        "src/layouts/AppShell.vue": { lines: 100, statements: 100, functions: 100, branches: 90 },
        "src/views/{SeriesDetail,GalleryDetail}.vue": {
          perFile: true,
          lines: 95,
          statements: 90,
          functions: 95,
          branches: 80,
        },
        "src/views/settings/{ContentPanel,DownloadsPanel,ImportPanel}.vue": {
          perFile: true,
          lines: 95,
          statements: 95,
          functions: 95,
          branches: 85,
        },
        "src/views/settings/{MangaDexConnectModal,TrackerConnectModal}.vue": {
          perFile: true,
          lines: 95,
          statements: 95,
          functions: 90,
          branches: 85,
        },
        "src/views/settings/AccountsPanel.vue": {
          lines: 95,
          statements: 95,
          functions: 90,
          branches: 90,
        },
        "src/views/settings/AppearancePanel.vue": {
          lines: 85,
          statements: 80,
          functions: 80,
          branches: 85,
        },
      },
    },
  },
});
