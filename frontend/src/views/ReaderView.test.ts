import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vite-plus/test";
import { createMemoryHistory, createRouter } from "vue-router";
import { fetchChapterDetail, fetchChapters, fetchSeries, putProgress } from "../api/queries";
import { useReaderSettings } from "../lib/readerSettings";
import type { Series, VolumeGroup } from "../types";
import ReaderView from "./ReaderView.vue";
vi.mock("../api/queries", () => ({
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
  });
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
  const wrapper = mount(ReaderView, { attachTo: document.body, global: { plugins: [router] } });
  await flushPromises();
  return { wrapper, router };
}
async function key(key: string) {
  window.dispatchEvent(new KeyboardEvent("keydown", { key, cancelable: true }));
  await flushPromises();
}

it("loads local chapter navigation and records position only after turning a page", async () => {
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
  expect(putProgress).toHaveBeenLastCalledWith("one", 2);
  await wrapper.get('[aria-label="Previous page"]').trigger("click");
  await flushPromises();
  expect(putProgress).toHaveBeenLastCalledWith("one", 1);
});

it("honors right-to-left page keys and click zones", async () => {
  useReaderSettings().direction = "rtl";
  const { wrapper } = await render();
  await key("ArrowLeft");
  expect(wrapper.get("img").attributes("alt")).toBe("Page 2");
  await key("ArrowRight");
  expect(wrapper.get("img").attributes("alt")).toBe("Page 1");
  await wrapper.get('[aria-label="Previous page"]').trigger("click");
  expect(wrapper.get("img").attributes("alt")).toBe("Page 2");
  await wrapper.get('[aria-label="Next page"]').trigger("click");
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
  await wrapper.get(".overflow-y-auto").trigger("click");
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
    ["width", "w-full"],
    ["both", "object-contain"],
    ["original", "max-w-none"],
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
