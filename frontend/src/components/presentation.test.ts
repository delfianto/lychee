import { flushPromises } from "@vue/test-utils";
import { expect, it, vi } from "vite-plus/test";
import { useAppApi, makeSeries, taskEvent } from "../test/appApi";
import { renderComponent as renderView } from "../test/views";
import { TestIntersectionObserver, TestResizeObserver } from "../test/observers";
import SeriesCollection from "./SeriesCollection.vue";
import SeriesRail from "./SeriesRail.vue";
import FeaturedCarousel from "./FeaturedCarousel.vue";
import SeriesDescription from "./SeriesDescription.vue";
import SeriesInfoPanel from "./SeriesInfoPanel.vue";
import SeriesListCard from "./SeriesListCard.vue";
import CountryFlag from "./CountryFlag.vue";
import ActivityIndicator from "./ActivityIndicator.vue";
import AddToListMenu from "./AddToListMenu.vue";
import Toaster from "./Toaster.vue";
import { toast } from "../lib/toast";
vi.mock("../api/client", async (original) => ({
  ...(await original<typeof import("../api/client")>()),
  api: (await import("../test/client")).testClient(),
}));
const api = useAppApi();

it("loads more only for a visible sentinel, resumes after loading, and disconnects", async () => {
  const { wrapper } = await renderView(SeriesCollection, {
    props: { series: [makeSeries()], density: "list", hasMore: true },
  });
  const collection = wrapper,
    observer = TestIntersectionObserver.instances[0]!;
  observer.emitEmpty();
  expect(collection.emitted("loadMore")).toBeUndefined();
  observer.emit(true);
  expect(collection.emitted("loadMore")).toHaveLength(1);
  await collection.setProps({ loading: true });
  observer.emit(true);
  expect(collection.emitted("loadMore")).toHaveLength(1);
  await collection.setProps({ loading: false });
  expect(collection.emitted("loadMore")).toHaveLength(2);
  await collection.setProps({ hasMore: false });
  observer.emit(true);
  expect(collection.emitted("loadMore")).toHaveLength(2);
  for (const density of ["gallery", "compact", "list"]) {
    await collection.setProps({ density });
    expect(collection.text()).toContain("Story s1");
  }
  await collection.setProps({ series: [], loading: false });
  expect(collection.text()).toContain("Nothing here yet");
  await collection.setProps({ loading: true });
  expect(collection.find(".animate-spin").exists()).toBe(true);
  wrapper.unmount();
  expect(observer.disconnect).toHaveBeenCalledOnce();
});

it("paginates a rail, translates wheel movement, and releases the wheel at edges", async () => {
  const { wrapper } = await renderView(SeriesRail, {
    props: { series: [makeSeries(), makeSeries("s2")] },
  });
  const track = wrapper.get(".overflow-x-auto");
  Object.defineProperty(track.element, "scrollLeft", {
    value: 0,
    writable: true,
    configurable: true,
  });
  const scroll = vi.spyOn(track.element, "scrollTo");
  await wrapper.get('[aria-label="Go to page 2"]').trigger("click");
  expect(scroll).toHaveBeenCalledWith({ left: 300, behavior: "smooth" });
  const wheel = (deltaY: number) => {
    const event = new WheelEvent("wheel", { deltaY, cancelable: true });
    track.element.dispatchEvent(event);
    return event;
  };
  expect(wheel(-20).defaultPrevented).toBe(false);
  expect(wheel(30).defaultPrevented).toBe(true);
  expect(track.element.scrollLeft).toBe(30);
  track.element.scrollLeft = 300;
  expect(wheel(20).defaultPrevented).toBe(false);
  await track.trigger("scroll");
  expect(wrapper.get('[aria-label="Go to page 2"]').classes()).toContain("bg-primary");
  TestResizeObserver.instances[0]!.emit();
  vi.spyOn(track.element, "scrollWidth", "get").mockReturnValue(300);
  expect(wheel(20).defaultPrevented).toBe(false);
  wrapper.unmount();
  expect(TestResizeObserver.instances[0]!.disconnect).toHaveBeenCalledOnce();
});

it("wraps featured slides and handles missing reading progress", async () => {
  const items = [
    makeSeries(),
    makeSeries("second", { lastReadChapter: 0, totalChapters: undefined, description: undefined }),
  ];
  const { wrapper } = await renderView(FeaturedCarousel, { props: { items } });
  expect(wrapper.get("h2 a").attributes("href")).toBe(`/series/${items[0]!.id}`);
  expect(wrapper.get("progress").attributes("value")).toBe("33");
  await wrapper.get('[aria-label="Next"]').trigger("click");
  expect(wrapper.get("h2").text()).toBe("Story second");
  expect(wrapper.get("progress").attributes("value")).toBe("0");
  await wrapper.get('[aria-label="Next"]').trigger("click");
  expect(wrapper.get("h2").text()).toBe("Story s1");
  await wrapper.get('[aria-label="Previous"]').trigger("click");
  await wrapper.get('[aria-label="Go to slide 1"]').trigger("click");
  expect(wrapper.get("h2").text()).toBe("Story s1");
  await wrapper.setProps({ items: [] });
  expect(wrapper.find("section").exists()).toBe(false);
});

it("escapes synopsis markup and renders optional namespace tags", async () => {
  const { wrapper } = await renderView(SeriesDescription, {
    props: {
      text: "A **bold** story <img src=x onerror=alert(1)>\n\n| Namespace | Tags |\n| --- | --- |\n| genre | action, drama |",
      clamp: true,
    },
  });
  expect(wrapper.find("strong").text()).toBe("bold");
  expect(wrapper.find("img").exists()).toBe(false);
  expect(wrapper.text()).toContain("action");
  const component = wrapper;
  await component.setProps({ showTagTable: false });
  expect(wrapper.find("table").exists()).toBe(false);
  await component.setProps({ text: null });
  expect(wrapper.text()).toBe("");
});

it("shows rich and sparse series metadata and limits tags in compact cards", async () => {
  const rich = makeSeries("s1", {
    favorite: true,
    tags: Array.from({ length: 8 }, (_, i) => ({
      id: String(i),
      name: `Tag ${i}`,
      group: "genre",
    })),
  });
  const { wrapper } = await renderView(SeriesListCard, { props: { series: rich, compact: true } });
  expect(wrapper.text()).toContain("+5");
  await wrapper.setProps({ compact: false });
  expect(wrapper.text()).toContain("+2");
  await wrapper.setProps({
    series: makeSeries("g1", {
      kind: "gallery",
      originCountry: undefined,
      rating: undefined,
      description: undefined,
      unreadCount: 0,
      availableChapters: 0,
    }),
  });
  expect(wrapper.find('a[href="/gallery/g1"]').exists()).toBe(true);
  wrapper.unmount();
  const info = await renderView(SeriesInfoPanel, { props: { series: rich } });
  expect(info.wrapper.text()).toContain("2024");
  expect(info.wrapper.text()).toContain("AniList");
  await info.wrapper.setProps({ series: makeSeries("s1", { year: undefined }) });
  expect(info.wrapper.text()).not.toContain("2024");
});

it("renders case-insensitive country flags and ignores unsupported countries", async () => {
  const { wrapper } = await renderView(CountryFlag, { props: { cc: "JP" } });
  expect(wrapper.get("img").attributes("alt")).toBe("JP");
  await wrapper.setProps({ cc: "xx" });
  expect(wrapper.find("img").exists()).toBe(false);
});

it("toggles list membership without navigating the parent card and handles no lists", async () => {
  const { wrapper, router } = await renderView(AddToListMenu, { props: { seriesId: "s1" } });
  await wrapper.get('[aria-label="Add to list"]').trigger("click");
  await wrapper.get("li a").trigger("click");
  await flushPromises();
  expect(api.db.collections[0]!.seriesIds).toEqual([]);
  await wrapper.get("li a").trigger("click");
  await flushPromises();
  expect(api.db.collections[0]!.seriesIds).toEqual(["s1"]);
  expect(router.currentRoute.value.path).toBe("/");
  wrapper.unmount();
  api.db.collections = [];
  const empty = await renderView(AddToListMenu, { props: { seriesId: "s1" } });
  expect(empty.wrapper.text()).toContain("No lists yet");
});

it("shows live task badges and toast variants, then returns to idle", async () => {
  const { wrapper } = await renderView(ActivityIndicator);
  expect(wrapper.find("[role=button]").exists()).toBe(false);
  for (const kind of ["thumbs", "scan", "download", "metadata", "other"])
    taskEvent(kind, "running", { detail: kind === "scan" ? "2/5" : null, progress: 40 });
  await flushPromises();
  expect(wrapper.text()).toContain("Thumbs");
  expect(wrapper.text()).toContain("DL");
  expect(wrapper.text()).toContain("Meta");
  expect(wrapper.text()).toContain("2/5");
  for (const kind of ["thumbs", "scan", "download", "metadata", "other"]) taskEvent(kind);
  await flushPromises();
  expect(wrapper.find("[role=button]").exists()).toBe(false);
  wrapper.unmount();
  const toasts = await renderView(Toaster);
  toast("Success");
  toast("Info", "info");
  toast("Error", "error");
  await flushPromises();
  expect(toasts.wrapper.text()).toContain("Success");
  expect(toasts.wrapper.text()).toContain("Info");
  expect(toasts.wrapper.text()).toContain("Error");
});
