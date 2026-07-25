import { describe, expect, it, vi } from "vitest";

import type { BrowseFilters } from "../types";
import { buildLibraryQuery, useSeriesList } from "./queries";

vi.mock("./client", () => ({
  api: { GET: vi.fn(async () => ({ data: { items: [], nextCursor: null }, error: undefined })) },
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
