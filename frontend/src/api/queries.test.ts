import { describe, expect, it, vi } from "vitest";

import type { BrowseFilters } from "../types";
import { buildLibraryQuery, deleteChapterLocal, fetchChapters, queueDownload, useSeriesList } from "./queries";

vi.mock("./client", () => ({
  api: {
    GET: vi.fn(async () => ({ data: { items: [], nextCursor: null }, error: undefined })),
    POST: vi.fn(async () => ({ data: undefined, error: undefined, response: { status: 200 } })),
    DELETE: vi.fn(async () => ({ data: undefined, error: undefined, response: { status: 200 } })),
  },
}));

function filters(overrides: Partial<BrowseFilters> = {}): BrowseFilters {
  return {
    query: "",
    tags: {},
    tagMode: "and",
    ratings: new Set(),
    demographics: new Set(),
    statuses: new Set(),
    readStates: new Set(),
    sort: "Recently Added",
    ...overrides,
  };
}

const base = { activeTab: "all", filters: filters(), sort: "Recently Added" };

describe("buildLibraryQuery", () => {
  it("maps library keys to kind / favorite / shelf", () => {
    expect(buildLibraryQuery("comics", base).kind).toBe("comic");
    expect(buildLibraryQuery("gallery", base).kind).toBe("gallery");
    expect(buildLibraryQuery("favorites", base).favorite).toBe(true);
    expect(buildLibraryQuery("reading", base).shelf).toBe("reading");
    expect(buildLibraryQuery("manga", base).kind).toBe("manga");
  });

  it("applies the active shelf tab (except on the reading route)", () => {
    expect(buildLibraryQuery("manga", { ...base, activeTab: "on_hold" }).shelf).toBe("on_hold");
    expect(buildLibraryQuery("reading", { ...base, activeTab: "on_hold" }).shelf).toBe("reading");
  });

  it("encodes tags with an exclusion prefix + mode, and trims the query", () => {
    const q = buildLibraryQuery("manga", {
      ...base,
      filters: filters({ query: "  berserk ", tags: { action: "include", horror: "exclude" }, tagMode: "or" }),
    });
    expect(q.q).toBe("berserk");
    expect(q.tags).toBe("action,-horror");
    expect(q.tagMode).toBe("or");
  });

  it("maps sort labels via SORT_MAP, defaulting unknown", () => {
    expect(buildLibraryQuery("manga", { ...base, sort: "Title" }).sort).toBe("title");
    expect(buildLibraryQuery("manga", { ...base, sort: "Nonsense" }).sort).toBe("recentlyAdded");
  });
});

describe("useSeriesList paging guard", () => {
  it("does not fetch on loadMore before the first reload", async () => {
    const { api } = await import("./client");
    vi.mocked(api.GET).mockClear();

    const list = useSeriesList();
    list.loadMore(); // sentinel fires on an empty grid — must be a no-op
    expect(api.GET).not.toHaveBeenCalled();

    await list.reload({ kind: "manga" }); // first real (filtered) load
    expect(api.GET).toHaveBeenCalledTimes(1);
  });
});

// eslint-disable-next-line @typescript-eslint/no-explicit-any -- minimal ApiSeries fixture
function seriesFixture(id: string): any {
  return {
    id,
    title: id,
    coverUrl: "",
    authors: [],
    artists: [],
    status: "ongoing",
    contentRating: "safe",
    demographic: "none",
    tags: [],
    chapterCount: 0,
    unreadCount: 0,
    favorite: false,
    availableChapters: 0,
  };
}

describe("useSeriesList stale-response guard", () => {
  it("keeps the newer reload's result even if the older, slower one resolves later", async () => {
    const { api } = await import("./client");
    type Resolver = (v: { data: unknown; error: undefined }) => void;
    const resolvers: Resolver[] = [];
    vi.mocked(api.GET).mockImplementation(
      () => new Promise((resolve) => resolvers.push(resolve as Resolver)) as ReturnType<typeof api.GET>,
    );

    const list = useSeriesList();
    const older = list.reload({ kind: "manga" }); // fired first, resolves second
    const newer = list.reload({ kind: "comic" }); // fired second, resolves first

    resolvers[1]!({ data: { items: [seriesFixture("comic-1")], nextCursor: null }, error: undefined });
    await newer;
    resolvers[0]!({ data: { items: [seriesFixture("manga-1")], nextCursor: null }, error: undefined });
    await older;

    expect(list.items.value.map((s) => s.id)).toEqual(["comic-1"]);
  });
});

describe("fetchChapters / toChapter defaults", () => {
  it("nullish-coalesces optional API fields to their UI defaults", async () => {
    const { api } = await import("./client");
    vi.mocked(api.GET).mockResolvedValueOnce({
      data: [
        {
          volume: null,
          chapters: [
            {
              id: null,
              volume: null,
              number: "1",
              title: null,
              group: null,
              language: "en",
              uploadedAt: null,
              read: null,
              comments: null,
              status: null,
              providerChapterId: null,
            },
          ],
        },
      ],
      error: undefined,
      response: { status: 200 },
    } as Awaited<ReturnType<typeof api.GET>>);

    const [group] = await fetchChapters("s1");
    const [chapter] = group!.chapters;
    expect(chapter).toMatchObject({
      id: null,
      title: undefined,
      group: undefined,
      uploadedAt: "",
      read: false,
      comments: 0,
      status: "downloaded",
      providerChapterId: null,
    });
  });
});

describe("queueDownload error handling", () => {
  it("resolves without throwing on success", async () => {
    const { api } = await import("./client");
    vi.mocked(api.POST).mockResolvedValueOnce({
      data: undefined,
      error: undefined,
      response: { status: 202 },
    } as Awaited<ReturnType<typeof api.POST>>);
    await expect(queueDownload("series-1")).resolves.toBeUndefined();
  });

  it("throws the backend's error message on failure", async () => {
    const { api } = await import("./client");
    vi.mocked(api.POST).mockResolvedValueOnce({
      data: undefined,
      error: { error: { code: "bad_request", message: "series is not linked to a provider" } },
      response: { status: 400 },
    } as Awaited<ReturnType<typeof api.POST>>);
    await expect(queueDownload("series-1")).rejects.toThrow("series is not linked to a provider");
  });

  it("falls back to a generic message when the error body has no message", async () => {
    const { api } = await import("./client");
    vi.mocked(api.POST).mockResolvedValueOnce({
      data: undefined,
      error: {},
      response: { status: 500 },
    } as Awaited<ReturnType<typeof api.POST>>);
    await expect(queueDownload("series-1")).rejects.toThrow("Download failed (500)");
  });
});

describe("deleteChapterLocal error handling", () => {
  it("returns the mapped result on success", async () => {
    const { api } = await import("./client");
    vi.mocked(api.DELETE).mockResolvedValueOnce({
      data: { mode: "local", redownloadable: false, seriesId: "s1" },
      error: undefined,
      response: { status: 200 },
    } as Awaited<ReturnType<typeof api.DELETE>>);
    await expect(deleteChapterLocal("c1")).resolves.toEqual({
      mode: "local",
      redownloadable: false,
      seriesId: "s1",
    });
  });

  it("throws the backend's error message on failure", async () => {
    const { api } = await import("./client");
    vi.mocked(api.DELETE).mockResolvedValueOnce({
      data: undefined,
      error: { error: { code: "not_found", message: "chapter 'c1' not found" } },
      response: { status: 404 },
    } as Awaited<ReturnType<typeof api.DELETE>>);
    await expect(deleteChapterLocal("c1")).rejects.toThrow("chapter 'c1' not found");
  });
});
