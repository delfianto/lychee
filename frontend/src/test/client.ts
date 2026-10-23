// Keep the client factory independent of task events so async API mocks cannot
// form an import cycle through the application harness.
import createClient from "openapi-fetch";
import type { paths } from "../api/schema";

export const testClient = () =>
  createClient<paths>({
    baseUrl: "http://localhost",
    fetch: (request) => globalThis.fetch(request),
  });
