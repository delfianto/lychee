import tailwindcss from "@tailwindcss/vite";
import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";

const useMocks = process.env.VITE_USE_MOCKS === "true";

export default defineConfig({
  plugins: [vue(), tailwindcss()],
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
