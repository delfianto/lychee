import { flushPromises } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useCollections } from "./collections";

vi.mock("../api/client", () => ({
  api: {
    GET: vi.fn(async () => ({ data: [], error: undefined, response: { status: 200 } })),
    POST: vi.fn(async () => ({ data: undefined, error: undefined, response: { status: 200 } })),
    PATCH: vi.fn(async () => ({ data: undefined, error: undefined, response: { status: 200 } })),
    DELETE: vi.fn(async () => ({ data: undefined, error: undefined, response: { status: 200 } })),
  },
}));

function apiCollection(id: string, seriesIds: string[] = []) {
  return { id, name: id, description: null, seriesIds, kind: null };
}

beforeEach(() => {
  setActivePinia(createPinia());
  vi.clearAllMocks();
});

describe("useCollections", () => {
  it("hasSeries is false for an unknown list or series", async () => {
    const store = useCollections();
    await flushPromises(); // let the store's own auto-refresh() (fired on creation) settle
    expect(store.hasSeries("missing-list", "s1")).toBe(false);
  });

  it("toggleSeries adds a series optimistically and POSTs, then removes and DELETEs", async () => {
    const { api } = await import("../api/client");
    // Consumed by the store's own auto-refresh() call, fired synchronously on creation.
    vi.mocked(api.GET).mockResolvedValueOnce({
      data: [apiCollection("l1")],
      error: undefined,
      response: { status: 200 },
    } as Awaited<ReturnType<typeof api.GET>>);

    const store = useCollections();
    await flushPromises();
    expect(store.hasSeries("l1", "s1")).toBe(false);

    await store.toggleSeries("l1", "s1");
    expect(store.hasSeries("l1", "s1")).toBe(true); // optimistic add reflected synchronously
    expect(api.POST).toHaveBeenCalledWith(
      "/api/collections/{collection_id}/series",
      expect.objectContaining({ params: { path: { collection_id: "l1" } }, body: { seriesId: "s1" } }),
    );

    await store.toggleSeries("l1", "s1");
    expect(store.hasSeries("l1", "s1")).toBe(false); // toggled back off
    expect(api.DELETE).toHaveBeenCalledWith(
      "/api/collections/{collection_id}/series/{series_id}",
      expect.objectContaining({ params: { path: { collection_id: "l1", series_id: "s1" } } }),
    );
  });

  it("toggleSeries on an unknown list is a no-op (no API call)", async () => {
    const { api } = await import("../api/client");
    const store = useCollections();
    await flushPromises();
    await store.toggleSeries("no-such-list", "s1");
    expect(api.POST).not.toHaveBeenCalled();
    expect(api.DELETE).not.toHaveBeenCalled();
  });

  it("removeSeries removes optimistically and DELETEs, independent of toggle state", async () => {
    const { api } = await import("../api/client");
    vi.mocked(api.GET).mockResolvedValueOnce({
      data: [apiCollection("l1", ["s1", "s2"])],
      error: undefined,
      response: { status: 200 },
    } as Awaited<ReturnType<typeof api.GET>>);

    const store = useCollections();
    await flushPromises();
    expect(store.hasSeries("l1", "s1")).toBe(true);

    await store.removeSeries("l1", "s1");
    expect(store.hasSeries("l1", "s1")).toBe(false);
    expect(store.hasSeries("l1", "s2")).toBe(true); // untouched
    expect(api.DELETE).toHaveBeenCalledWith(
      "/api/collections/{collection_id}/series/{series_id}",
      expect.objectContaining({ params: { path: { collection_id: "l1", series_id: "s1" } } }),
    );
  });
});
