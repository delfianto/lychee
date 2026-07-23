import tailwindcss from "@tailwindcss/vite";
import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  server: {
    port: 5173,
    // Proxy API calls to the FastAPI backend during dev.
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
});
