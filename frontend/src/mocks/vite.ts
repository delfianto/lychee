// HTTP fallback for LAN previews, where Service Workers are unavailable.
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";
import type { ReadableStream } from "node:stream/web";
import { getResponse } from "msw";
import type { Plugin } from "vite-plus";
import { handlers } from "./handlers";

export function mockApi(): Plugin {
  return {
    name: "lychee-mock-api",
    configureServer(server) {
      server.middlewares.use(async (req, res, next) => {
        if (!req.url?.startsWith("/api/")) return next();
        try {
          const origin = `http://${req.headers.host}`;
          const method = req.method ?? "GET";
          const chunks: Buffer[] = [];
          if (method !== "GET" && method !== "HEAD") {
            for await (const chunk of req) chunks.push(Buffer.from(chunk));
          }
          const headers = new Headers();
          for (const [key, value] of Object.entries(req.headers)) {
            if (value !== undefined)
              headers.set(key, Array.isArray(value) ? value.join(", ") : value);
          }
          const request = new Request(new URL(req.url, origin), {
            method,
            headers,
            body: chunks.length ? Buffer.concat(chunks) : undefined,
          });
          const response = await getResponse(handlers, request, { baseUrl: origin });
          if (!response) {
            res.writeHead(404, { "Content-Type": "application/json" });
            res.end(JSON.stringify({ error: { message: "No mock API handler for this request" } }));
            return;
          }
          res.writeHead(response.status, Object.fromEntries(response.headers));
          if (response.body) await pipeline(Readable.fromWeb(response.body as ReadableStream), res);
          else res.end();
        } catch (error) {
          if (!res.destroyed) next(error);
        }
      });
    },
  };
}
