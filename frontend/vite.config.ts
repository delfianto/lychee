import tailwindcss from "@tailwindcss/vite";
import vue from "@vitejs/plugin-vue";
import { defineConfig, lazyPlugins } from "vite-plus";

const useMocks = process.env.VITE_USE_MOCKS === "true";

export default defineConfig({
  fmt: {
    ignorePatterns: ["public/**", "src/api/schema.d.ts"],
  },
  lint: {
    jsPlugins: [{ name: "vite-plus", specifier: "vite-plus/oxlint-plugin" }],
    rules: { "vite-plus/prefer-vite-plus-imports": "error" },
    // vue-tsc checks scripts and Vue templates through the native bridge.
    // Standalone tsgo cannot resolve SFC props and would report false errors.
    options: { typeAware: true, typeCheck: false },
  },
  plugins: lazyPlugins(() => [vue(), tailwindcss()]),
  server: {
    port: 5173,
    // Proxy API calls to the FastAPI backend during dev — disabled under
    // VITE_USE_MOCKS so the MSW service worker intercepts /api instead.
    proxy: useMocks
      ? undefined
      : {
          "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
        },
  },
});
