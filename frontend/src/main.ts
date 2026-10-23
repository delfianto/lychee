import { createApp } from "vue";
import { createPinia } from "pinia";

import App from "./App.vue";
import { router } from "./router";
import "./style.css";

async function bootstrap(): Promise<void> {
  // Plain HTTP LAN previews use the Vite mock API instead of a Service Worker.
  if (import.meta.env.DEV && import.meta.env.VITE_USE_MOCKS === "true" && window.isSecureContext) {
    const { worker } = await import("./mocks/browser");
    await worker.start({
      onUnhandledFrame: "bypass",
      quiet: true,
      serviceWorker: { options: { updateViaCache: "none" } },
    });
  }
  createApp(App).use(createPinia()).use(router).mount("#app");
}

void bootstrap();
