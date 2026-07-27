// Browser-side MSW worker — started from main.ts when VITE_USE_MOCKS=true.
import { setupWorker } from "msw/browser";
import { handlers } from "./handlers";

export const worker = setupWorker(...handlers);
