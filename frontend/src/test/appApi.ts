import { installObservers } from "./observers";
import createClient from "openapi-fetch";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, beforeEach, expect, vi } from "vite-plus/test";
import { connectTaskStream, useTasks, type Task } from "../api/events";
import type { paths } from "../api/schema";
import type { Series, Collection } from "../types";
import type {
  Provider,
  Tracker,
  LibraryRow,
  TaxonomyItem,
  DownloadTask,
  ImportConfig,
  About,
  SyncState,
  Chapter,
  VolumeGroup,
  GalleryMediaItem,
} from "../api/client";

export const testClient = () =>
  createClient<paths>({
    baseUrl: "http://localhost",
    fetch: (request) => globalThis.fetch(request),
  });
export function makeSeries(id = "s1", patch: Partial<Series> = {}): Series {
  return {
    id,
    title: `Story ${id}`,
    coverUrl: `/covers/${id}`,
    authors: ["Writer"],
    artists: ["Artist"],
    status: "ongoing",
    contentRating: "safe",
    demographic: "shonen",
    tags: [{ id: "action", name: "Action", group: "genre" }],
    chapterCount: 2,
    unreadCount: 1,
    year: 2024,
    description: "A **bold** story.",
    lastReadChapter: 1,
    totalChapters: 3,
    originCountry: "jp",
    rating: 8.5,
    favorite: false,
    kind: "manga",
    libraryStatus: "reading",
    provider: "mangadex",
    availableChapters: 1,
    ...patch,
  };
}
export function makeChapter(id: string | null, patch: Partial<Chapter> = {}): Chapter {
  return {
    id,
    volume: 1,
    number: id ?? "3",
    language: "en",
    uploadedAt: "2026-01-01T00:00:00Z",
    read: false,
    comments: 0,
    status: id ? "downloaded" : "available",
    providerChapterId: id ? null : "remote-3",
    ...patch,
  };
}
export function makeDownload(
  id: string,
  status = "queued",
  patch: Partial<DownloadTask> = {},
): DownloadTask {
  return {
    id,
    series: { ...makeSeries(id), favorite: false, availableChapters: 0 },
    chapter: "Ch. 1",
    status,
    progress: 0,
    ...patch,
  };
}
export function makeTax(id = "action", patch: Partial<TaxonomyItem> = {}): TaxonomyItem {
  return {
    id,
    name: id === "action" ? "Action" : id,
    category: "genre",
    uses: 2,
    enabled: true,
    system: false,
    aliases: [],
    ...patch,
  };
}
function seed() {
  return {
    series: [
      makeSeries(),
      makeSeries("s2", {
        title: "Second story",
        originCountry: "kr",
        chapterCount: 1,
        unreadCount: 0,
        rating: undefined,
        provider: null,
      }),
      makeSeries("g1", {
        title: "Gallery",
        kind: "gallery",
        artists: ["Model"],
        source: "Franchise",
        characters: ["Hero"],
        imageCount: 3,
        provider: null,
      }),
    ],
    collections: [
      { id: "list", name: "Weekend", seriesIds: ["s1"], kind: "manga" },
    ] as Collection[],
    providers: [
      {
        id: "mangadex",
        name: "MangaDex",
        enabled: true,
        language: "en",
        autoMatch: true,
        fetchCovers: true,
        dataSaver: false,
        connected: false,
        accountName: null,
      },
    ] as Provider[],
    trackers: [
      { id: "anilist", name: "AniList", authKind: "oauth", connected: false, syncOnRead: false },
      {
        id: "mangaupdates",
        name: "MangaUpdates",
        authKind: "credentials",
        connected: true,
        accountName: "Reader",
        syncOnRead: true,
      },
      {
        id: "novelupdates",
        name: "NovelUpdates",
        authKind: "unsupported",
        connected: false,
        syncOnRead: false,
      },
    ] as Tracker[],
    thumbnailStorage: {
      path: null as string | null,
      defaultPath: "/storage/thumbnails",
      effectivePath: "/storage/thumbnails",
    },
    libraries: [
      {
        id: "lib",
        name: "Manga root",
        path: "/media/Manga",
        kind: "manga",
        enabled: true,
        seriesCount: 2,
        lastScan: null,
      },
    ] as LibraryRow[],
    taxonomy: [
      makeTax(),
      makeTax("drama", { name: "Drama", enabled: false }),
      makeTax("safe", { name: "General", category: "content_rating", system: true }),
      makeTax("shonen", { category: "demographic", system: true }),
    ],
    downloads: [] as DownloadTask[],
    downloadConfig: { parallelDownloads: 1 },
    importConfig: {
      enabled: true,
      quality: 75,
      filenamePattern: "{series} - {chapter}",
      patternPresets: [{ name: "Default", pattern: "{series} - {chapter}" }],
    } as ImportConfig,
    about: {
      version: "1.2.3",
      platform: "Linux",
      database: "SQLite",
      started: "2026-01-01T00:00:00Z",
      uptimeSeconds: 90000,
    } as About,
    sync: {
      lastSync: null,
      autoEveryMinutes: 0,
      newChapters: 2,
      syncing: false,
      paused: false,
      parallelSyncs: 1,
      jobs: [],
    } as SyncState,
    chapters: [
      {
        volume: 1,
        chapters: [
          makeChapter("2", { number: "2", title: "Later", read: true }),
          makeChapter("1", { number: "1", title: "Start" }),
          makeChapter(null, { number: "3" }),
        ],
      },
    ] as VolumeGroup[],
    images: [
      { index: 0, kind: "image", url: "/image", thumbUrl: "/thumb", posterUrl: null },
      { index: 1, kind: "gif", url: "/gif", thumbUrl: "", posterUrl: "/poster" },
      { index: 2, kind: "video", url: "/video.mp4", thumbUrl: "", posterUrl: null },
    ] as GalleryMediaItem[],
    candidates: [
      {
        providerSeriesId: "md1",
        title: "Matched story",
        year: 2024,
        status: "ongoing",
        coverUrl: "/matched",
      },
      { providerSeriesId: "md2", title: "No cover", year: null, status: null, coverUrl: null },
    ],
  };
}
interface RecordedRequest {
  method: string;
  path: string;
  query: URLSearchParams;
  body: Record<string, unknown>;
}
class TestEventSource {
  static source: TestEventSource;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  constructor(_url: string) {
    TestEventSource.source = this;
  }
  emit(event: string, task: Task) {
    this.onmessage?.(new MessageEvent("message", { data: JSON.stringify({ event, task }) }));
  }
}
export function taskEvent(
  kind: string,
  status: "running" | "done" | "failed" = "done",
  extra: Partial<Task> = {},
) {
  const task: Task = {
    id: `test-${kind}`,
    kind,
    label: `${kind} task`,
    status,
    progress: status === "done" ? 100 : 0,
    ...extra,
  };
  TestEventSource.source.emit(`${kind}.${status === "running" ? "progress" : status}`, task);
}
export function useAppApi() {
  let db = seed();
  const requests: RecordedRequest[] = [];
  const unexpected: string[] = [];
  const server = setupServer(
    http.all("http://localhost/api/*", async ({ request }) => {
      const url = new URL(request.url),
        path = url.pathname,
        method = request.method;
      const text =
        method !== "GET" && request.headers.get("content-type")?.includes("application/json")
          ? await request.text()
          : "";
      const body: Record<string, unknown> = text ? JSON.parse(text) : {};
      if (path === "/api/import/upload") {
        const form = await request.formData();
        body.kind = form.get("kind");
        body.files = form
          .getAll("files")
          .map((file) => (typeof file === "string" ? file : file.name));
      }
      requests.push({ method, path, query: url.searchParams, body });
      const json = (value: unknown) =>
        new HttpResponse(JSON.stringify(value), {
          headers: { "Content-Type": "application/json" },
        });
      const done = () => new HttpResponse(null, { status: 204 });
      const task = () =>
        json({ id: "task", kind: "scan", label: "Test task", status: "running", progress: 0 });
      if (path.endsWith("/chapter-availability"))
        return json({
          status: "ready",
          language: "en",
          availableLanguages: ["en"],
          availableCount: 2,
          totalCount: 2,
        });
      if (path === "/api/dashboard") {
        const kindsParam = url.searchParams.get("recentlyAddedKinds") ?? "manga";
        const kinds =
          kindsParam === "none" ? [] : kindsParam.split(",").filter((k) => k.length > 0);
        return json({
          stats: { series: db.series.length, unreadChapters: 2, reading: 1 },
          continueReading: db.series.filter((s) => s.kind !== "gallery"),
          readingList: db.series.filter((s) => s.libraryStatus === "reading").slice(0, 12),
          recentUpdates: db.series.slice(0, 1).map((series) => ({
            series,
            volume: 1,
            chapter: "2",
            updatedAt: new Date().toISOString(),
          })),
          recentlyAdded: db.series.filter((s) => kinds.includes(s.kind ?? "manga")),
        });
      }
      if (path === "/api/libraries/summary")
        return json([
          { key: "manga", title: "Manga", sizeGb: 1.5 },
          { key: "empty", title: "Empty", sizeGb: 0 },
        ]);
      if (path === "/api/search")
        return json(
          db.series.filter((s) =>
            s.title.toLowerCase().includes((url.searchParams.get("q") ?? "").toLowerCase()),
          ),
        );
      if (path.startsWith("/api/updates"))
        return json({
          items: db.series.slice(0, 2).map((series) => ({
            series,
            volume: series.id === "s1" ? 1 : null,
            chapter: "2",
            updatedAt: new Date().toISOString(),
          })),
          nextCursor: null,
        });
      if (path === "/api/series" && method === "GET") {
        const kindParam = url.searchParams.get("kind");
        const kinds = kindParam ? kindParam.split(",").filter(Boolean) : null;
        return json({
          items: db.series.filter((s) => !kinds || kinds.includes(s.kind ?? "manga")),
          nextCursor: null,
        });
      }
      const seriesMatch = path.match(/^\/api\/series\/([^/]+)(?:\/(.+))?$/);
      if (seriesMatch) {
        const [, id, action] = seriesMatch;
        const item = db.series.find((s) => s.id === id);
        if (!item)
          return HttpResponse.json({ error: { message: "Series not found" } }, { status: 404 });
        if (!action) {
          if (method === "PATCH") Object.assign(item, body);
          return json(item);
        }
        if (action === "chapters") return json(db.chapters);
        if (action === "related") return json(db.series.filter((s) => s.id !== id));
        if (action === "art") return json({ images: ["/art1", "/art2"] });
        if (action === "images") return json({ items: db.images, nextCursor: null });
        if (action === "match-candidates") return json(db.candidates);
        if (action === "match" && method === "DELETE") {
          item.provider = null;
          return done();
        }
        if (action === "match" || action === "refresh") return task();
      }
      if (path.startsWith("/api/chapters/")) {
        if (method === "DELETE")
          return json({ mode: "provider", redownloadable: true, seriesId: "s1" });
        if (path.endsWith("/progress")) return done();
        if (path.endsWith("/buffer")) {
          const cid = path.split("/").at(-2) ?? "1";
          const start = Number(body.startPage ?? 1);
          const count = Number(body.preloadPages ?? 4);
          return json({
            chapterId: cid,
            pageCount: 3,
            bufferedPages: Array.from(
              { length: Math.min(3 - start + 1, count) },
              (_, i) => start + i,
            ),
          });
        }
        return json({
          id: path.split("/").at(-1),
          seriesId: "s1",
          volume: 1,
          number: "1",
          title: "Start",
          pageCount: 3,
        });
      }
      if (path === "/api/collections") {
        if (method === "POST") {
          const created: Collection = { id: "new-list", name: String(body.name), seriesIds: [] };
          db.collections.push(created);
          return json(created);
        }
        return json(db.collections);
      }
      const collectionMatch = path.match(
        /^\/api\/collections\/([^/]+)(?:\/series(?:\/([^/]+))?)?$/,
      );
      if (collectionMatch) {
        const [, id, seriesId] = collectionMatch;
        const item = db.collections.find((c) => c.id === id);
        if (!item)
          return HttpResponse.json({ error: { message: "List not found" } }, { status: 404 });
        if (path.includes("/series")) {
          if (method === "POST") item.seriesIds.push(String(body.seriesId));
          else item.seriesIds = item.seriesIds.filter((s) => s !== seriesId);
          return done();
        }
        if (method === "PATCH") Object.assign(item, body);
        if (method === "DELETE") {
          db.collections = db.collections.filter((c) => c.id !== id);
          return done();
        }
        return json({ ...item, series: db.series.filter((s) => item.seriesIds.includes(s.id)) });
      }
      if (path === "/api/providers") return json(db.providers);
      const providerMatch = path.match(/^\/api\/providers\/([^/]+)(?:\/(.+))?$/);
      if (providerMatch) {
        const [, id, action] = providerMatch;
        const item = db.providers.find((p) => p.id === id)!;
        if (!action) Object.assign(item, body);
        else if (action === "connect") {
          item.connected = true;
          item.accountName = String(body.username);
        } else if (action === "disconnect") item.connected = false;
        return done();
      }
      if (path === "/api/trackers") return json(db.trackers);
      const trackerMatch = path.match(/^\/api\/trackers\/([^/]+)(?:\/(.+))?$/);
      if (trackerMatch) {
        const [, id, action] = trackerMatch;
        const item = db.trackers.find((t) => t.id === id)!;
        if (action === "connect")
          return json({ authorizeUrl: "https://auth.example/authorize?state=nonce" });
        if (action === "login" || action === "callback") item.connected = true;
        if (method === "PATCH") Object.assign(item, body);
        if (method === "DELETE") item.connected = false;
        return done();
      }
      if (path === "/api/libraries/thumbnail-storage") {
        if (method === "PUT") {
          db.thumbnailStorage.path = body.path as string | null;
          db.thumbnailStorage.effectivePath =
            db.thumbnailStorage.path ?? db.thumbnailStorage.defaultPath;
        }
        return json(db.thumbnailStorage);
      }
      if (path === "/api/libraries") {
        if (method === "POST") {
          db.libraries.push({
            id: "new-lib",
            name: String(body.name),
            path: String(body.path),
            kind: String(body.kind),
            enabled: true,
            seriesCount: 0,
          });
          return json(db.libraries.at(-1));
        }
        return json(db.libraries);
      }
      if (path.startsWith("/api/libraries/")) {
        if (method === "DELETE")
          db.libraries = db.libraries.filter((l) => l.id !== path.split("/").at(-1));
        return task();
      }
      if (path === "/api/taxonomy") {
        if (method === "POST") {
          const tag = makeTax("new-tag", {
            name: String(body.name),
            category: String(body.category),
          });
          db.taxonomy.push(tag);
          return json(tag);
        }
        return json({ items: db.taxonomy, total: db.taxonomy.length, page: 1, pageSize: 500 });
      }
      if (path === "/api/taxonomy/refresh") return task();
      const taxMatch = path.match(/^\/api\/taxonomy\/([^/]+)(?:\/aliases(?:\/([^/]+))?)?$/);
      if (taxMatch) {
        const [, id, aliasId] = taxMatch;
        const item = db.taxonomy.find((t) => t.id === id)!;
        if (path.includes("aliases")) {
          if (method === "POST")
            item.aliases.push({ id: "new-alias", name: String(body.name), tagId: id! });
          else item.aliases = item.aliases.filter((a) => a.id !== aliasId);
        } else if (method === "PATCH") Object.assign(item, body);
        else db.taxonomy = db.taxonomy.filter((t) => t.id !== id);
        return json(item);
      }
      if (path === "/api/downloads") {
        if (method === "GET") return json(db.downloads);
        if (body.action === "pause-all")
          db.downloads.forEach((d) => {
            if (d.status === "queued") d.status = "paused";
          });
        else if (body.action === "resume-all")
          db.downloads.forEach((d) => {
            if (d.status === "paused") d.status = "queued";
          });
        else if (body.action === "cancel-all") db.downloads = [];
        else return task();
        return json(db.downloads);
      }
      if (path === "/api/downloads/config") {
        if (method === "PATCH") {
          db.downloadConfig.parallelDownloads = Number(body.parallelDownloads ?? 1);
        }
        return json(db.downloadConfig);
      }
      if (path === "/api/downloads/clear-completed") {
        db.downloads = db.downloads.filter((d) => d.status !== "done");
        return done();
      }
      const dlMatch = path.match(/^\/api\/downloads\/([^/]+)(?:\/(.+))?$/);
      if (dlMatch) {
        const [, id, action] = dlMatch;
        if (method === "DELETE") db.downloads = db.downloads.filter((d) => d.id !== id);
        else {
          const item = db.downloads.find((d) => d.id === id);
          if (item) item.status = action === "pause" ? "paused" : "queued";
        }
        return json(db.downloads);
      }
      if (path === "/api/sync") return method === "GET" ? json(db.sync) : task();
      if (path === "/api/sync/config") {
        db.sync.parallelSyncs = Number(body.parallelSyncs ?? 1);
        return json(db.sync);
      }
      if (path === "/api/sync/control") {
        const action = typeof body.action === "string" ? body.action : "";
        const jobId = typeof body.jobId === "string" ? body.jobId : null;
        const jobs = db.sync.jobs ?? [];
        if (action === "clear-completed") {
          db.sync.jobs = jobs.filter(
            (j) => j.status !== "done" && j.status !== "failed" && j.status !== "cancelled",
          );
        } else if (jobId) {
          const job = jobs.find((j) => j.id === jobId);
          if (job) {
            if (action === "pause") job.status = "paused";
            else if (action === "resume") job.status = "queued";
            else if (action === "cancel") job.status = "cancelled";
          }
        } else if (action === "pause-all") {
          db.sync.paused = true;
          jobs.forEach((j) => {
            if (j.status === "queued" || j.status === "running") j.status = "paused";
          });
        } else if (action === "resume-all") {
          db.sync.paused = false;
          jobs.forEach((j) => {
            if (j.status === "paused") j.status = "queued";
          });
        } else if (action === "cancel-all") {
          db.sync.paused = false;
          jobs.forEach((j) => {
            if (j.status === "queued" || j.status === "running" || j.status === "paused") {
              j.status = "cancelled";
            }
          });
        }
        return json(db.sync);
      }
      if (path === "/api/import/config") {
        if (method === "PATCH") Object.assign(db.importConfig, body);
        return json(db.importConfig);
      }
      if (path === "/api/import" || path === "/api/import/upload") return task();
      if (path === "/api/about") return json(db.about);
      if (path === "/api/fs")
        return json({
          root: "/media",
          path: url.searchParams.get("path") ?? "/media",
          parent: null,
          entries: [{ name: "Manga", path: "/media/Manga", kind: "dir" }],
        });
      unexpected.push(`${method} ${path}`);
      return HttpResponse.json({ error: { message: "Unexpected test request" } }, { status: 500 });
    }),
  );
  beforeAll(() => server.listen({ onUnhandledFrame: "error" }));
  beforeEach(() => {
    installObservers();
    db = seed();
    requests.length = 0;
    unexpected.length = 0;
    vi.stubGlobal("EventSource", TestEventSource);
    connectTaskStream();
    for (const task of useTasks().activeTasks.value)
      TestEventSource.source.emit(`${task.kind}.done`, { ...task, status: "done" });
  });
  afterEach(() => {
    server.resetHandlers();
    expect(unexpected, "Unexpected HTTP requests").toEqual([]);
  });
  afterAll(() => server.close());
  return {
    get db() {
      return db;
    },
    requests,
    server,
    failNext(method: string, path: string, message = "Rejected by server", status = 409) {
      server.use(
        http.all(
          `http://localhost${path}`,
          ({ request }) =>
            request.method === method
              ? HttpResponse.json({ error: { message } }, { status })
              : undefined,
          { once: true },
        ),
      );
    },
    writes() {
      return requests.filter((r) => r.method !== "GET");
    },
  };
}
