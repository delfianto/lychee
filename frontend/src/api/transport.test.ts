import createClient from "openapi-fetch";
import { flushPromises } from "@vue/test-utils";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vite-plus/test";
import type { paths } from "./schema";
import * as queries from "./queries";
import * as settings from "./settingsQueries";

// Only supply an origin for Node's Request; exercise the real typed HTTP client.
vi.mock("./client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./client")>()),
  api: createClient<paths>({
    baseUrl: "http://localhost",
    fetch: (request) => globalThis.fetch(request),
  }),
}));
const server = setupServer();
beforeAll(() => server.listen({ onUnhandledFrame: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
const root = "http://localhost";
function series(id: string, extra: Record<string, unknown> = {}) {
  return {
    id,
    title: id,
    coverUrl: `/covers/${id}`,
    authors: ["Author"],
    artists: [],
    status: "ongoing",
    contentRating: "safe",
    demographic: "none",
    tags: [],
    chapterCount: 2,
    unreadCount: 1,
    favorite: false,
    availableChapters: 0,
    ...extra,
  };
}
const denied = () =>
  HttpResponse.json(
    { error: { code: "denied", message: "Server refused the change" } },
    { status: 409 },
  );

describe("read mapping through HTTP", () => {
  it("maps dashboard series, updates, nullable metadata, and tag groups", async () => {
    const item = series("s1", {
      year: null,
      userRating: 7,
      tags: [{ id: "action", name: "Action", group: "genre" }],
    });
    server.use(
      http.get(`${root}/api/dashboard`, () =>
        HttpResponse.json({
          stats: { series: 1, unreadChapters: 1, reading: 0 },
          continueReading: [item],
          readingList: [item],
          recentUpdates: [
            { series: item, volume: 1, chapter: "2", updatedAt: new Date().toISOString() },
          ],
          recentlyAdded: [item],
        }),
      ),
    );
    const result = await queries.fetchDashboard();
    expect(result.stats.series).toBe(1);
    expect(result.continueReading[0]).toMatchObject({
      id: "s1",
      year: undefined,
      userRating: 7,
      tags: [{ id: "action", group: "genre" }],
    });
    expect(result.readingList[0]?.id).toBe("s1");
    expect(result.recentUpdates[0]?.updatedAt).toBe("now");
    expect(result.recentlyAdded[0]?.title).toBe("s1");
    server.use(http.get(`${root}/api/dashboard`, denied));
    await expect(queries.fetchDashboard()).rejects.toThrow("Failed to load dashboard");
  });

  it("sends chapter language/order and maps local and remote chapter defaults", async () => {
    server.use(
      http.get(`${root}/api/series/:id/chapters`, ({ request, params }) => {
        expect(params.id).toBe("s1");
        expect(new URL(request.url).searchParams.get("language")).toBe("ja");
        expect(new URL(request.url).searchParams.get("order")).toBe("desc");
        return HttpResponse.json([
          {
            volume: null,
            chapters: [
              { id: "local", volume: null, number: "1", language: "ja", uploadedAt: null },
              {
                id: null,
                volume: null,
                number: "2",
                title: "Remote",
                language: "ja",
                uploadedAt: new Date().toISOString(),
                status: "remote",
                providerChapterId: "remote-id",
                read: true,
                comments: 3,
              },
            ],
          },
        ]);
      }),
    );
    const result = await queries.fetchChapters("s1", { language: "ja", order: "desc" });
    expect(result[0]?.chapters).toEqual([
      expect.objectContaining({
        id: "local",
        title: undefined,
        uploadedAt: "",
        read: false,
        comments: 0,
        status: "downloaded",
        providerChapterId: null,
      }),
      expect.objectContaining({
        id: null,
        title: "Remote",
        read: true,
        status: "remote",
        providerChapterId: "remote-id",
      }),
    ]);
  });

  it("follows every gallery cursor and retains earlier images on a later API error", async () => {
    const cursors: (string | null)[] = [];
    server.use(
      http.get(`${root}/api/series/:id/images`, ({ request }) => {
        const cursor = new URL(request.url).searchParams.get("cursor");
        cursors.push(cursor);
        return HttpResponse.json({
          items: [
            {
              index: cursor ? 1 : 0,
              kind: "image",
              url: `/page/${cursor ?? "first"}`,
              thumbUrl: "/thumb",
              posterUrl: cursor ? "/poster" : null,
            },
          ],
          nextCursor: cursor ? null : "next",
        });
      }),
    );
    expect(await queries.fetchGalleryImages("s1")).toEqual([
      { index: 0, kind: "image", url: "/page/first", thumbUrl: "/thumb", posterUrl: null },
      { index: 1, kind: "image", url: "/page/next", thumbUrl: "/thumb", posterUrl: "/poster" },
    ]);
    expect(cursors).toEqual([null, "next"]);
    server.use(
      http.get(`${root}/api/series/:id/images`, ({ request }) =>
        new URL(request.url).searchParams.has("cursor")
          ? denied()
          : HttpResponse.json({
              items: [{ index: 0, kind: "image", url: "/first", thumbUrl: "/thumb" }],
              nextCursor: "next",
            }),
      ),
    );
    expect(await queries.fetchGalleryImages("s1")).toHaveLength(1);
  });

  it("groups filter taxonomy and separates editable rating labels", async () => {
    server.use(
      http.get(`${root}/api/taxonomy`, ({ request }) => {
        expect(new URL(request.url).searchParams.get("pageSize")).toBe("500");
        return HttpResponse.json({
          items: [
            { id: "action", name: "Action", category: "genre" },
            { id: "safe", name: "General", category: "content_rating" },
            { id: "shonen", name: "Boys", category: "demographic" },
          ],
        });
      }),
    );
    expect(await queries.fetchTagGroups()).toEqual([
      { group: "Genre", tags: [{ id: "action", name: "Action" }] },
    ]);
    expect(await queries.fetchRatingLabels()).toEqual({
      contentRating: { safe: "General" },
      demographic: { shonen: "Boys" },
    });
  });

  it("pages once at a time and can retry a failed initial grid request", async () => {
    let calls = 0;
    server.use(
      http.get(`${root}/api/series`, ({ request }) => {
        calls++;
        expect(new URL(request.url).searchParams.get("kind")).toBe("comic");
        if (calls === 1) return denied();
        const cursor = new URL(request.url).searchParams.get("cursor");
        return HttpResponse.json({
          items: [series(cursor ? "second" : "first")],
          nextCursor: cursor ? null : "p2",
        });
      }),
    );
    const list = queries.useSeriesList();
    await list.reload({ kind: "comic" });
    expect(list.failed.value).toBe(true);
    list.retry();
    await vi.waitFor(() => expect(list.failed.value).toBe(false));
    list.loadMore();
    list.loadMore();
    await vi.waitFor(() => expect(list.items.value.map((s) => s.id)).toEqual(["first", "second"]));
    expect(list.hasMore.value).toBe(false);
    list.loadMore();
    await flushPromises();
    expect(calls).toBe(3);
  });

  it("chooses only existing random ids and returns null for an empty library", async () => {
    server.use(
      http.get(`${root}/api/series`, () =>
        HttpResponse.json({ items: [series("first"), series("last")] }),
      ),
    );
    vi.spyOn(Math, "random").mockReturnValue(0.99);
    expect(await queries.randomSeriesId()).toBe("last");
    server.use(http.get(`${root}/api/series`, () => HttpResponse.json({ items: [] })));
    expect(await queries.randomSeriesId()).toBeNull();
  });
});

describe("settings writes and errors through HTTP", () => {
  it("creates a folder then reloads its parent, and explains conflicts", async () => {
    const listing = {
      root: "/media",
      path: "/media",
      parent: null,
      entries: [{ name: "New", path: "/media/New", kind: "dir" }],
    };
    server.use(
      http.post(`${root}/api/fs/mkdir`, async ({ request }) => {
        expect(await request.json()).toEqual({ parent: "/media", name: "New" });
        return HttpResponse.json({ path: "/media/New" });
      }),
      http.get(`${root}/api/fs`, ({ request }) => {
        expect(new URL(request.url).searchParams.get("path")).toBe("/media");
        return HttpResponse.json(listing);
      }),
    );
    expect(await settings.makeDirectory("/media", "New")).toEqual(listing);
    server.use(http.post(`${root}/api/fs/mkdir`, denied));
    await expect(settings.makeDirectory("/media", "New")).rejects.toThrow("already exists");
  });

  it("returns tracker authorization URLs and sends callback credentials", async () => {
    const credentials = {
      clientId: "client",
      clientSecret: "secret",
      redirectUri: "http://localhost/callback",
    };
    server.use(
      http.post(`${root}/api/trackers/:id/connect`, async ({ request, params }) => {
        expect(params.id).toBe("anilist");
        expect(await request.json()).toEqual(credentials);
        return HttpResponse.json({ authorizeUrl: "https://auth.example/authorize" });
      }),
      http.post(`${root}/api/trackers/:id/callback`, async ({ request }) => {
        expect(await request.json()).toEqual({
          code: "code",
          redirectUri: credentials.redirectUri,
          state: "state",
        });
        return new HttpResponse(null, { status: 204 });
      }),
    );
    expect(await settings.beginTrackerConnect("anilist", credentials)).toBe(
      "https://auth.example/authorize",
    );
    await expect(
      settings.completeTrackerConnect("anilist", {
        code: "code",
        redirectUri: credentials.redirectUri,
        state: "state",
      }),
    ).resolves.toBeUndefined();
  });

  it.each([
    [
      "library",
      "/api/libraries",
      () => settings.addLibrary({ name: "Manga", path: "/missing", kind: "manga" }),
    ],
    ["import", "/api/import", () => settings.startImport("/missing", "manga")],
    ["taxonomy", "/api/taxonomy", () => settings.createTaxonomyTag("Action", "genre")],
    [
      "login",
      "/api/trackers/mangaupdates/login",
      () => settings.loginTracker("mangaupdates", { username: "u", password: "p" }),
    ],
    [
      "connect",
      "/api/providers/mangadex/connect",
      () =>
        settings.connectMangaDex({
          username: "u",
          password: "p",
          clientId: "c",
          clientSecret: "s",
        }),
    ],
    [
      "auth",
      "/api/trackers/anilist/connect",
      () =>
        settings.beginTrackerConnect("anilist", {
          clientId: "c",
          clientSecret: "s",
          redirectUri: "/callback",
        }),
    ],
    [
      "callback",
      "/api/trackers/anilist/callback",
      () =>
        settings.completeTrackerConnect("anilist", {
          code: "c",
          state: "s",
          redirectUri: "/callback",
        }),
    ],
  ] as const)("surfaces backend reasons for rejected %s requests", async (_label, path, action) => {
    server.use(http.post(`${root}${path}`, denied));
    await expect(action()).rejects.toThrow("Server refused the change");
  });

  it("distinguishes a refreshed bulk queue from an accepted background operation", async () => {
    server.use(
      http.post(`${root}/api/downloads`, async ({ request }) => {
        expect(await request.json()).toEqual({ action: "pause-all" });
        return HttpResponse.json([]);
      }),
    );
    expect(await settings.bulkDownloadAction("pause-all")).toEqual({ rows: [] });
    server.use(
      http.post(`${root}/api/downloads`, () => HttpResponse.json({ id: "task" }, { status: 202 })),
    );
    expect(await settings.bulkDownloadAction("resume-all")).toEqual({ rows: null });
    server.use(http.post(`${root}/api/downloads`, denied));
    await expect(settings.bulkDownloadAction("cancel-all")).rejects.toThrow("Server refused");
  });
});

describe("HTTP request contracts", () => {
  it.each([
    [
      "PATCH",
      "/api/providers/md",
      { enabled: false, language: "ja" },
      () => settings.updateProvider("md", { enabled: false, language: "ja" }),
    ],
    ["POST", "/api/providers/md/disconnect", undefined, () => settings.disconnectProvider("md")],
    ["POST", "/api/providers/md/sync", undefined, () => settings.syncProvider("md")],
    ["DELETE", "/api/trackers/al", undefined, () => settings.disconnectTracker("al")],
    [
      "PATCH",
      "/api/trackers/al",
      { syncOnRead: false },
      () => settings.setTrackerSyncOnRead("al", false),
    ],
    ["POST", "/api/libraries/scan", undefined, () => settings.scanAllLibraries()],
    ["POST", "/api/libraries/lib/scan", undefined, () => settings.scanLibrary("lib")],
    ["DELETE", "/api/libraries/lib", undefined, () => settings.deleteLibrary("lib")],
    [
      "PATCH",
      "/api/taxonomy/tag",
      { enabled: false },
      () => settings.setTaxonomyEnabled("tag", false),
    ],
    [
      "PATCH",
      "/api/taxonomy/tag",
      { name: "Renamed" },
      () => settings.renameTaxonomyTag("tag", "Renamed"),
    ],
    ["DELETE", "/api/taxonomy/tag", undefined, () => settings.deleteTaxonomyTag("tag")],
    ["POST", "/api/taxonomy/refresh", undefined, () => settings.refreshTaxonomy()],
    [
      "POST",
      "/api/taxonomy/tag/aliases",
      { name: "Alias" },
      () => settings.addTaxonomyAlias("tag", "Alias"),
    ],
    [
      "DELETE",
      "/api/taxonomy/tag/aliases/alias",
      undefined,
      () => settings.deleteTaxonomyAlias("tag", "alias"),
    ],
    ["POST", "/api/sync", undefined, () => settings.runSync()],
    ["POST", "/api/downloads/task/retry", undefined, () => settings.retryDownload("task")],
    ["DELETE", "/api/downloads/task", undefined, () => settings.deleteDownloadTask("task")],
    ["POST", "/api/downloads/clear-completed", undefined, () => settings.clearCompletedDownloads()],
    [
      "PATCH",
      "/api/import/config",
      { quality: 65, enabled: false },
      () => settings.updateImportConfig({ quality: 65, enabled: false }),
    ],
    [
      "PATCH",
      "/api/series/s1",
      { favorite: false, rating: 8 },
      () => queries.patchSeries("s1", { favorite: false, rating: 8 }),
    ],
    [
      "POST",
      "/api/series/s1/match",
      { providerSeriesId: "md-id", provider: "mangadex" },
      () => queries.matchSeries("s1", "md-id"),
    ],
    ["POST", "/api/series/s1/refresh", undefined, () => queries.refreshSeries("s1")],
    ["DELETE", "/api/series/s1/match", undefined, () => queries.unlinkMatch("s1")],
    [
      "PUT",
      "/api/chapters/c1/progress",
      { page: 4, completed: true },
      () => queries.putProgress("c1", 4, true),
    ],
  ] as const)("sends %s %s with the expected wire body", async (method, path, body, action) => {
    let received = false;
    server.use(
      http.all(`${root}${path}`, async ({ request }) => {
        expect(request.method).toBe(method);
        if (body !== undefined) expect(await request.json()).toEqual(body);
        received = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    await action();
    expect(received).toBe(true);
  });

  it.each([
    ["/api/providers", settings.fetchProviders, [{ id: "md", enabled: false }]],
    ["/api/trackers", settings.fetchTrackers, [{ id: "al", syncOnRead: true }]],
    ["/api/libraries", settings.fetchLibraryRows, [{ id: "lib", seriesCount: 2 }]],
    ["/api/downloads", settings.fetchDownloadTasks, [{ id: "task", progress: 50 }]],
    ["/api/sync", settings.fetchSyncState, { status: "running" }],
    ["/api/import/config", settings.fetchImportConfig, { quality: 65 }],
    ["/api/about", settings.fetchAbout, { version: "test" }],
    ["/api/libraries/summary", queries.fetchLibrarySummaries, [{ key: "manga", sizeGb: 1 }]],
  ] as const)(
    "returns %s payloads without losing false/zero values",
    async (path, action, payload) => {
      server.use(http.get(`${root}${path}`, () => HttpResponse.json(payload)));
      expect(await action()).toEqual(payload);
    },
  );

  it("handles download pause/resume and empty read responses", async () => {
    server.use(
      http.post(`${root}/api/downloads/task/pause`, () => HttpResponse.json([])),
      http.post(`${root}/api/downloads/task/resume`, () => new HttpResponse(null, { status: 204 })),
    );
    expect(await settings.pauseDownload("task")).toEqual([]);
    expect(await settings.resumeDownload("task")).toBeNull();
    server.use(http.get(`${root}/api/*`, () => new HttpResponse(null, { status: 204 })));
    for (const action of [
      settings.fetchProviders,
      settings.fetchTrackers,
      settings.fetchTaxonomy,
      settings.fetchDownloadTasks,
    ])
      expect(await action()).toEqual([]);
    for (const action of [settings.fetchSyncState, settings.fetchImportConfig, settings.fetchAbout])
      expect(await action()).toBeNull();
    await expect(settings.fetchLibraryRows()).rejects.toThrow("load libraries");
    await expect(settings.browsePath()).rejects.toThrow("Couldn't read");
  });

  it("maps detail, search, related, collection, art, and library gallery responses", async () => {
    server.use(
      http.get(`${root}/api/series/s1`, () =>
        HttpResponse.json(
          series("s1", {
            year: 2024,
            kind: "manga",
            libraryStatus: "reading",
            description: "Synopsis",
          }),
        ),
      ),
      http.get(`${root}/api/chapters/c1`, () =>
        HttpResponse.json({
          id: "c1",
          seriesId: "s1",
          volume: null,
          number: "1",
          title: null,
          pageCount: 5,
        }),
      ),
      http.get(`${root}/api/search`, ({ request }) => {
        expect(new URL(request.url).searchParams.get("q")).toBe("Story");
        return HttpResponse.json([series("s1")]);
      }),
      http.get(`${root}/api/series/s1/related`, () => HttpResponse.json([series("related")])),
      http.get(`${root}/api/series/s1/art`, () => HttpResponse.json({ images: ["/art"] })),
      http.get(`${root}/api/collections/list`, () =>
        HttpResponse.json({ name: "Weekend", series: [series("s1")] }),
      ),
      http.get(`${root}/api/series`, ({ request }) => {
        expect(new URL(request.url).searchParams.get("kind")).toBe("gallery");
        return HttpResponse.json({ items: [series("gallery")] });
      }),
      http.get(`${root}/api/series/s1/match-candidates`, ({ request }) => {
        expect(new URL(request.url).searchParams.get("q")).toBe("Story");
        return HttpResponse.json([{ providerSeriesId: "md", title: "Story" }]);
      }),
      http.post(`${root}/api/chapters/c1/buffer`, async ({ request }) => {
        expect(await request.json()).toEqual({ startPage: 2, preloadPages: 3 });
        return HttpResponse.json({
          chapterId: "c1",
          pageCount: 5,
          bufferedPages: [2, 3, 4],
        });
      }),
    );
    expect(await queries.bufferChapterPages("c1", 2, 3)).toEqual({
      chapterId: "c1",
      pageCount: 5,
      bufferedPages: [2, 3, 4],
    });
    expect(await queries.fetchSeries("s1")).toMatchObject({
      year: 2024,
      libraryStatus: "reading",
      description: "Synopsis",
    });
    expect(await queries.fetchChapterDetail("c1")).toEqual({
      id: "c1",
      seriesId: "s1",
      volume: null,
      number: "1",
      title: undefined,
      pageCount: 5,
    });
    expect((await queries.searchSeries("Story"))[0]?.id).toBe("s1");
    expect((await queries.fetchRelated("s1"))[0]?.id).toBe("related");
    expect(await queries.fetchArt("s1")).toEqual(["/art"]);
    expect(await queries.fetchCollection("list")).toMatchObject({
      name: "Weekend",
      series: [{ id: "s1" }],
    });
    expect((await queries.fetchGalleries())[0]?.id).toBe("gallery");
    expect(await queries.fetchMatchCandidates("s1", "Story")).toEqual([
      { providerSeriesId: "md", title: "Story", year: null, status: null, coverUrl: null },
    ]);
  });

  it("returns safe read fallbacks while detail lookups reject missing resources", async () => {
    server.use(http.get(`${root}/api/*`, denied));
    for (const action of [
      () => queries.fetchUpdates(),
      () => queries.fetchUpdates(true),
      () => queries.searchSeries("none"),
      () => queries.fetchRelated("s1"),
      () => queries.fetchArt("s1"),
      () => queries.fetchChapters("s1"),
      () => queries.fetchMatchCandidates("s1"),
    ])
      expect(await action()).toEqual([]);
    await expect(queries.fetchGalleries()).rejects.toThrow("Server refused the change");
    expect(await queries.fetchCollection("list")).toBeNull();
    await expect(queries.fetchSeries("missing")).rejects.toThrow("Series not found");
    await expect(queries.fetchChapterDetail("missing")).rejects.toThrow("Chapter not found");
    await expect(queries.fetchLibrarySummaries()).rejects.toThrow("Failed to load");
  });

  it("maps both update feeds and preserves their limits", async () => {
    const requested: string[] = [];
    server.use(
      http.get(`${root}/api/updates*`, ({ request }) => {
        const url = new URL(request.url);
        requested.push(url.pathname);
        expect(url.searchParams.get("limit")).toBe("7");
        return HttpResponse.json({
          items: [
            {
              series: series("s1"),
              volume: null,
              chapter: "2",
              updatedAt: new Date().toISOString(),
            },
          ],
        });
      }),
    );
    expect((await queries.fetchUpdates(false, 7))[0]?.series.id).toBe("s1");
    expect((await queries.fetchUpdates(true, 7))[0]?.chapter).toBe("2");
    expect(requested).toEqual(["/api/updates", "/api/updates/unread"]);
  });
});

it("sends creator roles and names, persists manual batches, and reports progress failures", async () => {
  server.use(
    http.get(`${root}/api/creators`, ({ request }) => {
      const url = new URL(request.url);
      expect(url.searchParams.get("role")).toBe("author");
      expect(url.searchParams.get("q")).toBe("A & B");
      return HttpResponse.json(["A & B"]);
    }),
    http.get(`${root}/api/search`, ({ request }) => {
      const url = new URL(request.url);
      expect(url.searchParams.get("author")).toBe("A & B");
      expect(url.searchParams.get("artist")).toBe("Artist");
      return HttpResponse.json([series("creator-match")]);
    }),
    http.put(`${root}/api/series/s1/read-status`, async ({ request }) => {
      expect(await request.json()).toEqual({
        chapterIds: ["c1", "adhoc:s1:remote"],
        completed: true,
      });
      return HttpResponse.json({ updated: 2 });
    }),
    http.put(`${root}/api/chapters/c1/progress`, denied),
  );
  expect(await queries.fetchCreatorNames("author", "A & B")).toEqual(["A & B"]);
  expect((await queries.searchSeries("", { author: "A & B", artist: "Artist" }))[0]?.id).toBe(
    "creator-match",
  );
  expect(await queries.markChaptersRead("s1", ["c1", "adhoc:s1:remote"], true)).toBe(2);
  await expect(queries.putProgress("c1", 4, true)).rejects.toThrow();
  server.use(http.get(`${root}/api/creators`, denied));
  await expect(queries.fetchCreatorNames("author", "Unavailable")).rejects.toThrow(
    "creator suggestions",
  );
});
