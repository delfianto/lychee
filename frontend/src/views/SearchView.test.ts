import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, expect, it, vi } from "vite-plus/test";
import { createMemoryHistory, createRouter } from "vue-router";
import { searchSeries } from "../api/queries";
import type { Series } from "../types";
import SearchView from "./SearchView.vue";
vi.mock("../api/queries", () => ({
  searchSeries: vi.fn(),
  fetchCreatorNames: vi.fn().mockResolvedValue([]),
}));
beforeEach(() => {
  vi.useFakeTimers();
  vi.mocked(searchSeries).mockReset().mockResolvedValue([]);
});
afterEach(() => vi.useRealTimers());
async function render(path = "/search") {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: "/search", component: SearchView }],
  });
  await router.push(path);
  await router.isReady();
  const wrapper = mount(SearchView, {
    global: { plugins: [router], stubs: { SeriesCollection: true } },
  });
  return { wrapper, router };
}
function result(id: string): Series {
  return { id, title: id } as Series;
}

it("debounces input, trims a submitted query, and responds to deep links", async () => {
  const { wrapper, router } = await render("/search?q=initial");
  expect(wrapper.get("input").element.value).toBe("initial");
  await wrapper.get("input").setValue("  latest  ");
  await vi.advanceTimersByTimeAsync(249);
  expect(searchSeries).not.toHaveBeenCalled();
  await vi.advanceTimersByTimeAsync(1);
  expect(searchSeries).toHaveBeenCalledExactlyOnceWith("latest", {});
  await wrapper.get("input").trigger("keyup.enter");
  await flushPromises();
  expect(router.currentRoute.value.query.q).toBe("latest");
  await router.replace("/search?q=linked");
  await flushPromises();
  expect(wrapper.get("input").element.value).toBe("linked");
  await wrapper.get("input").setValue(" ");
  await wrapper.get("input").trigger("keyup.enter");
  await flushPromises();
  expect(router.currentRoute.value.query).toEqual({});
  expect(wrapper.text()).toContain("Type to search");
});

it("keeps newer search results when an older request completes last", async () => {
  let resolveOld!: (value: Series[]) => void;
  vi.mocked(searchSeries)
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveOld = resolve;
        }),
    )
    .mockResolvedValueOnce([result("new")]);
  const { wrapper } = await render("/search?q=old");
  await vi.advanceTimersByTimeAsync(250);
  await wrapper.get("input").setValue("new");
  await vi.advanceTimersByTimeAsync(250);
  expect(wrapper.getComponent({ name: "SeriesCollection" }).props("series")).toEqual([
    result("new"),
  ]);
  resolveOld([result("old")]);
  await flushPromises();
  expect(wrapper.getComponent({ name: "SeriesCollection" }).props("series")).toEqual([
    result("new"),
  ]);
});

it("cancels a pending debounce on unmount", async () => {
  const { wrapper } = await render("/search?q=pending");
  wrapper.unmount();
  await vi.advanceTimersByTimeAsync(250);
  expect(searchSeries).not.toHaveBeenCalled();
});

it("opens creator deep links and combines free-text author and artist filters", async () => {
  const { wrapper, router } = await render("/search?author=Writer%20A");
  expect(wrapper.get("details").attributes("open")).toBeDefined();
  expect(wrapper.get<HTMLInputElement>('[aria-label="Author / mangaka"]').element.value).toBe(
    "Writer A",
  );
  await vi.advanceTimersByTimeAsync(250);
  expect(searchSeries).toHaveBeenLastCalledWith("", { author: "Writer A" });
  await wrapper.get('[aria-label="Author / mangaka"]').setValue("Writer A");
  await wrapper.get('[aria-label="Artist"]').setValue("Arbitrary artist");
  await vi.advanceTimersByTimeAsync(250);
  expect(searchSeries).toHaveBeenLastCalledWith("", {
    author: "Writer A",
    artist: "Arbitrary artist",
  });
  await wrapper.get('[aria-label="Search all series"]').trigger("keyup.enter");
  await flushPromises();
  expect(router.currentRoute.value.query).toEqual({
    author: "Writer A",
    artist: "Arbitrary artist",
  });
  await router.replace("/search?artist=Different");
  await flushPromises();
  await vi.advanceTimersByTimeAsync(250);
  expect(searchSeries).toHaveBeenLastCalledWith("", { artist: "Different" });
});
