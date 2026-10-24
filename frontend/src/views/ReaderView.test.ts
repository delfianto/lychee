import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vite-plus/test";
import { createMemoryHistory, createRouter, RouterView } from "vue-router";
import {
  bufferChapterPages,
  fetchChapterDetail,
  fetchChapters,
  fetchSeries,
  putProgress,
} from "../api/queries";
import { useReaderSettings } from "../lib/readerSettings";
import type { Series, VolumeGroup } from "../types";
import ReaderView from "./ReaderView.vue";
vi.mock("../api/queries", () => ({
  bufferChapterPages: vi.fn(),
  fetchChapterDetail: vi.fn(),
  fetchChapters: vi.fn(),
  fetchSeries: vi.fn(),
  putProgress: vi.fn(),
}));
beforeEach(() => {
  vi.clearAllMocks();
  Object.assign(useReaderSettings(), {
    mode: "single",
    direction: "ltr",
    fit: "height",
    background: "dark",
    preloadPages: 4,
  });
  vi.mocked(bufferChapterPages).mockImplementation(async (id, startPage = 1, preloadPages = 4) => ({
    chapterId: id,
    pageCount: 6,
    bufferedPages: Array.from({ length: preloadPages }, (_, i) => startPage + i),
  }));
  vi.mocked(fetchChapterDetail).mockImplementation(async (id) => ({
    id,
    seriesId: "series",
    volume: null,
    number: id === "one" ? "1" : "2",
    title: id === "one" ? "Start" : undefined,
    pageCount: 3,
  }));
  vi.mocked(fetchSeries).mockResolvedValue({ id: "series", title: "Test series" } as Series);
  vi.mocked(fetchChapters).mockResolvedValue([
    {
      volume: null,
      chapters: [
        { id: "two", number: "2", status: "downloaded" },
        { id: null, number: "3", status: "remote" },
        { id: "one", number: "1", status: "downloaded" },
      ],
    },
  ] as VolumeGroup[]);
  vi.mocked(putProgress).mockResolvedValue(undefined);
});
async function render() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/read/:id", component: ReaderView },
      { path: "/series/:id", component: { template: "<div>Series</div>" } },
    ],
  });
  await router.push("/read/one");
  await router.isReady();
  const wrapper = mount(RouterView, { attachTo: document.body, global: { plugins: [router] } });
  await flushPromises();
  return { wrapper, router };
}
async function key(key: string) {
  window.dispatchEvent(new KeyboardEvent("keydown", { key, cancelable: true }));
  await flushPromises();
}

it("records loaded pages immediately and preserves the furthest position when going back", async () => {
  const { wrapper } = await render();
  expect(wrapper.text()).toContain("Test series");
  expect(wrapper.text()).toContain("Ch. 1 · Start");
  expect(wrapper.findAll("option").map((option) => option.attributes("value"))).toEqual([
    "one",
    "two",
  ]);
  expect(putProgress).not.toHaveBeenCalled();
  await key("ArrowLeft");
  expect(wrapper.get("img").attributes("alt")).toBe("Page 1");
  await key("ArrowRight");
  expect(wrapper.get("img").attributes("src")).toBe("/api/chapters/one/pages/2");
  await wrapper.get("img").trigger("load");
  await flushPromises();
  expect(putProgress).toHaveBeenLastCalledWith("one", 2, undefined);
  await wrapper.get('[aria-label="Previous page"]').trigger("click");
  await flushPromises();
  await wrapper.get("img").trigger("load");
  await flushPromises();
  expect(putProgress).toHaveBeenLastCalledWith("one", 2, undefined);
});

it("honors right-to-left page keys and click zones", async () => {
  useReaderSettings().direction = "rtl";
  const { wrapper } = await render();
  await key("ArrowLeft");
  expect(wrapper.get("img").attributes("alt")).toBe("Page 2");
  await key("ArrowRight");
  expect(wrapper.get("img").attributes("alt")).toBe("Page 1");
  const area = wrapper.get('[aria-label="Reading area"]');
  vi.spyOn(area.element, "getBoundingClientRect").mockReturnValue(new DOMRect(0, 0, 400, 600));
  await area.trigger("click", { clientX: 50 });
  expect(wrapper.get("img").attributes("alt")).toBe("Page 2");
  await area.trigger("click", { clientX: 350 });
  expect(wrapper.get("img").attributes("alt")).toBe("Page 1");
});

it("offers the next local chapter after the last page and returns to the series at the end", async () => {
  const { wrapper, router } = await render();
  for (let i = 0; i < 3; i++) await key("ArrowRight");
  const next = wrapper.findAll("button").find((button) => button.text() === "Next chapter")!;
  expect(next.isVisible()).toBe(true);
  await next.trigger("click");
  await flushPromises();
  expect(router.currentRoute.value.path).toBe("/read/two");
  expect(wrapper.get("img").attributes("alt")).toBe("Page 1");
  expect(wrapper.text()).toContain("Ch. 2");
  for (let i = 0; i < 3; i++) await key("ArrowRight");
  expect(wrapper.text()).toContain("That was the last chapter.");
  await wrapper
    .findAll("button")
    .find((button) => button.text() === "Back to series")!
    .trigger("click");
  await flushPromises();
  expect(router.currentRoute.value.path).toBe("/series/series");
});

it("renders double and strip modes and ignores page keys in strip mode", async () => {
  const { wrapper } = await render();
  const settings = useReaderSettings();
  settings.mode = "double";
  await flushPromises();
  expect(wrapper.findAll("img")).toHaveLength(2);
  settings.mode = "longstrip";
  await flushPromises();
  expect(wrapper.findAll("img")).toHaveLength(3);
  expect(wrapper.find('[aria-label="Next page"]').exists()).toBe(false);
  await key("ArrowRight");
  expect(putProgress).not.toHaveBeenCalled();
  await wrapper.get('[aria-label="Reading area"]').trigger("click");
  expect(wrapper.get("header").isVisible()).toBe(false);
});

it("applies fit and background settings and closes settings before navigating back", async () => {
  const { wrapper, router } = await render();
  const settings = useReaderSettings();
  const back = vi.spyOn(router, "back").mockImplementation(() => {});
  await wrapper.get('[aria-label="Settings"]').trigger("click");
  expect(wrapper.get("aside").isVisible()).toBe(true);
  await key("Escape");
  expect(wrapper.get("aside").isVisible()).toBe(false);
  expect(back).not.toHaveBeenCalled();
  await key("Escape");
  expect(back).toHaveBeenCalledTimes(1);
  for (const [fit, css] of [
    ["width", "reader-fit-width"],
    ["both", "reader-fit-both"],
    ["original", "reader-fit-original"],
  ] as const) {
    settings.fit = fit;
    await flushPromises();
    expect(wrapper.get("img").classes()).toContain(css);
  }
  settings.background = "black";
  await flushPromises();
  expect(wrapper.classes()).toContain("bg-black");
  settings.background = "sepia";
  await flushPromises();
  expect(wrapper.classes()).toContain("reader-sepia");
  wrapper.unmount();
  await key("ArrowRight");
  expect(putProgress).not.toHaveBeenCalled();
});

it("ignores an older chapter load that finishes after a route change", async () => {
  let resolveOld!: (detail: Awaited<ReturnType<typeof fetchChapterDetail>>) => void;
  vi.mocked(fetchChapterDetail).mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        resolveOld = resolve;
      }),
  );
  const { wrapper, router } = await render();
  await router.push("/read/two");
  await flushPromises();
  expect(wrapper.get("img").attributes("src")).toBe("/api/chapters/two/pages/1");
  resolveOld({ id: "one", seriesId: "old", volume: null, number: "1", pageCount: 20 });
  await flushPromises();
  expect(wrapper.get("img").attributes("src")).toBe("/api/chapters/two/pages/1");
  expect(fetchSeries).not.toHaveBeenCalledWith("old");
});

it("keeps click navigation on the scrolling surface and resets scroll for each new page or fit", async () => {
  const { wrapper } = await render();
  const area = wrapper.get('[aria-label="Reading area"]');
  const element = area.element as HTMLElement;
  vi.spyOn(element, "getBoundingClientRect").mockReturnValue(new DOMRect(0, 0, 400, 600));
  element.scrollTop = 500;
  element.scrollLeft = 250;
  await area.trigger("click", { clientX: 350 });
  await flushPromises();
  expect(wrapper.get("img").attributes("alt")).toBe("Page 2");
  expect(element.scrollTop).toBe(0);
  expect(element.scrollLeft).toBe(0);
  await area.trigger("click", { clientX: 50 });
  expect(wrapper.get("img").attributes("alt")).toBe("Page 1");
  await area.trigger("click", { clientX: 200 });
  expect(wrapper.get("header").isVisible()).toBe(false);
  await area.trigger("click", { clientX: 200 });
  expect(wrapper.get("header").isVisible()).toBe(true);
  element.scrollTop = 500;
  useReaderSettings().fit = "width";
  await flushPromises();
  expect(element.scrollTop).toBe(0);
});

it("gives the last unpaired page the whole width in double mode", async () => {
  const { wrapper } = await render();
  useReaderSettings().mode = "double";
  await flushPromises();
  const area = wrapper.get('[aria-label="Reading area"]');
  expect((area.element as HTMLElement).style.getPropertyValue("--reader-columns")).toBe("2");
  await wrapper.get('[aria-label="Page"]').setValue(3);
  await flushPromises();
  expect(wrapper.findAll("img")).toHaveLength(1);
  expect((area.element as HTMLElement).style.getPropertyValue("--reader-columns")).toBe("1");
});

it("buffers undownloaded ad-hoc chapters using preloadPages and prefetches on page turn", async () => {
  useReaderSettings().preloadPages = 3;
  vi.mocked(fetchChapters).mockResolvedValue([
    {
      volume: null,
      chapters: [
        { id: null, number: "5", status: "available", providerChapterId: "pc-5" },
        { id: "one", number: "1", status: "downloaded" },
      ],
    },
  ] as VolumeGroup[]);
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/read/:id", component: ReaderView },
      { path: "/series/:id", component: { template: "<div>Series</div>" } },
    ],
  });
  await router.push("/read/adhoc:series:pc-5");
  await router.isReady();
  const wrapper = mount(RouterView, { attachTo: document.body, global: { plugins: [router] } });
  await flushPromises();

  expect(bufferChapterPages).toHaveBeenCalledWith("adhoc:series:pc-5", 1, 3);
  expect(fetchChapterDetail).toHaveBeenCalledWith("adhoc:series:pc-5", 3);
  expect(wrapper.findAll("option").map((o) => o.attributes("value"))).toEqual([
    "one",
    "adhoc:series:pc-5",
  ]);

  await key("ArrowRight");
  expect(bufferChapterPages).toHaveBeenLastCalledWith("adhoc:series:pc-5", 2, 3);

  await wrapper.get('[aria-label="Settings"]').trigger("click");
  const preloadInput = wrapper.get('[aria-label="Ad-hoc preload pages"]');
  await preloadInput.setValue("6");
  await preloadInput.trigger("change");
  expect(useReaderSettings().preloadPages).toBe(6);
});

it("saves a one-page chapter as soon as its image loads, including remote reads", async () => {
  vi.mocked(fetchChapterDetail).mockImplementation(async (id) => ({
    id,
    seriesId: "series",
    volume: null,
    number: "1",
    pageCount: 1,
  }));
  const { wrapper, router } = await render();
  expect(putProgress).not.toHaveBeenCalled();
  await wrapper.get("img").trigger("load");
  await flushPromises();
  expect(putProgress).toHaveBeenLastCalledWith("one", 1, true);
  await router.push("/read/adhoc:series:remote");
  await flushPromises();
  await wrapper.get("img").trigger("load");
  await flushPromises();
  expect(putProgress).toHaveBeenLastCalledWith("adhoc:series:remote", 1, true);
});

it("marks the last double spread read after its second image loads", async () => {
  useReaderSettings().mode = "double";
  vi.mocked(fetchChapterDetail).mockImplementation(async (id) => ({
    id,
    seriesId: "series",
    volume: null,
    number: "1",
    pageCount: 4,
  }));
  const { wrapper } = await render();
  await key("ArrowRight");
  expect(wrapper.findAll("img").map((img) => img.attributes("alt"))).toEqual(["Page 3", "Page 4"]);
  await wrapper.findAll("img")[0]!.trigger("load");
  await flushPromises();
  expect(putProgress).toHaveBeenLastCalledWith("one", 3, undefined);
  await wrapper.findAll("img")[1]!.trigger("load");
  await flushPromises();
  expect(putProgress).toHaveBeenLastCalledWith("one", 4, true);
  await key("ArrowLeft");
  expect(wrapper.get("img").attributes("alt")).toBe("Page 1");
});

it("completes a long strip only at the bottom of the loaded last image", async () => {
  useReaderSettings().mode = "longstrip";
  const { wrapper } = await render();
  const area = wrapper.get('[aria-label="Reading area"]');
  let offset = 0;
  vi.spyOn(area.element, "getBoundingClientRect").mockImplementation(
    () => new DOMRect(0, 0, 400, 600),
  );
  const images = wrapper.findAll("img");
  images.forEach((image, index) =>
    vi
      .spyOn(image.element, "getBoundingClientRect")
      .mockImplementation(() => new DOMRect(0, index * 800 - offset, 400, 800)),
  );
  for (const image of images) await image.trigger("load");
  await flushPromises();
  expect(putProgress).toHaveBeenLastCalledWith("one", 1, undefined);
  offset = 1500;
  await area.trigger("scroll");
  await flushPromises();
  expect(putProgress).toHaveBeenLastCalledWith("one", 2, undefined);
  offset = 1800;
  await area.trigger("scroll");
  await flushPromises();
  expect(putProgress).toHaveBeenLastCalledWith("one", 3, true);
  expect(wrapper.text()).toContain("Next chapter");
  await wrapper
    .findAll("button")
    .find((b) => b.text() === "Next chapter")!
    .trigger("click");
  await flushPromises();
  expect(wrapper.get("img").attributes("src")).toContain("/two/");
});

it("shows a failed progress save and lets the reader retry", async () => {
  vi.mocked(putProgress).mockRejectedValueOnce(new Error("Connection lost"));
  const { wrapper } = await render();
  await wrapper.get("img").trigger("load");
  await flushPromises();
  expect(wrapper.get('[role="alert"]').text()).toContain("Connection lost");
  await wrapper
    .findAll("button")
    .find((b) => b.text() === "Retry save")!
    .trigger("click");
  await flushPromises();
  expect(wrapper.find('[role="alert"]').exists()).toBe(false);
  document.dispatchEvent(new Event("visibilitychange"));
  window.dispatchEvent(new Event("pagehide"));
});

it("flushes completion before leaving the reader and reports failures on navigation", async () => {
  const { wrapper, router } = await render();
  vi.mocked(putProgress).mockRejectedValue(new Error("Offline"));
  await wrapper.get("img").trigger("load");
  await flushPromises();
  await router.push("/series/series");
  await flushPromises();
  expect(router.currentRoute.value.path).toBe("/series/series");
  expect(vi.mocked(putProgress).mock.calls.length).toBeGreaterThan(1);
});
