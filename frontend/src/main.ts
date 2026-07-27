import { createApp } from "vue";
import { createPinia } from "pinia";

import App from "./App.vue";
import { router } from "./router";
import "./style.css";

async function bootstrap(): Promise<void> {
  if (import.meta.env.DEV && import.meta.env.VITE_USE_MOCKS === "true") {
    const { worker } = await import("./mocks/browser");
    await worker.start({
      onUnhandledRequest: "bypass",
      quiet: true,
      serviceWorker: { options: { updateViaCache: "none" } },
    });
  }
  createApp(App).use(createPinia()).use(router).mount("#app");
}

void bootstrap();
