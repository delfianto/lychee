import { flushPromises } from "@vue/test-utils";
import { http, HttpResponse } from "msw";
import { expect, it, vi } from "vite-plus/test";
import { useAppApi, makeSeries, taskEvent } from "../test/appApi";
import { renderView, click, input } from "../test/views";
import LibraryHome from "./LibraryHome.vue";
import LibraryView from "./LibraryView.vue";
import GalleryView from "./GalleryView.vue";
import AddedView from "./AddedView.vue";
import ChapterFeedView from "./ChapterFeedView.vue";
import ListsView from "./ListsView.vue";
import ListDetailView from "./ListDetailView.vue";
import FilterPanel from "../components/FilterPanel.vue";
import ConfirmDialog from "../components/ConfirmDialog.vue";
import { useDensity, useListsDefaultTab, useRecentlyAddedKinds } from "../lib/density";
vi.mock("../api/client", async (original) => ({
  ...(await original<typeof import("../api/client")>()),
  api: (await import("../test/appApi")).testClient(),
}));
const api = useAppApi();

it("shows the synced reading shelf without local progress and refreshes when sync finishes", async () => {
  api.db.series = [
    makeSeries("remote", { title: "Synced title", chapterCount: 0, unreadCount: 0 }),
  ];
  api.server.use(
    http.get("http://localhost/api/dashboard", () =>
      HttpResponse.json({
        stats: { series: api.db.series.length, unreadChapters: 0, reading: api.db.series.length },
        continueReading: [],
        readingList: api.db.series,
        recentUpdates: [],
        recentlyAdded: [],
      }),
    ),
  );
  const { wrapper } = await renderView(LibraryHome);
  expect(wrapper.text()).toContain("On your reading list");
  expect(wrapper.text()).toContain("Synced title");
  expect(wrapper.text()).not.toContain("Continue reading");
  expect(wrapper.text()).not.toContain("Recent updates");
  expect(wrapper.get('[aria-label="See your full reading list"]').attributes("href")).toBe(
    "/reading",
  );
  expect(wrapper.find('a[href="/series/remote"]').exists()).toBe(true);
  api.db.series.push(makeSeries("next", { title: "Newly synced title", chapterCount: 0 }));
  taskEvent("import");
  await vi.waitFor(() => expect(wrapper.text()).toContain("Newly synced title"));
  wrapper.unmount();
  const requestCount = api.requests.length;
  taskEvent("import");
  await flushPromises();
  expect(api.requests.length).toBe(requestCount);
});

it("hides the reading-list rail when the shelf is empty and filters recently added by configured kinds", async () => {
  useRecentlyAddedKinds().recentlyAddedKinds.value = ["manga"];
  api.db.series.forEach((series) => {
    series.libraryStatus = "completed";
  });
  const { wrapper } = await renderView(LibraryHome);
  expect(wrapper.text()).not.toContain("On your reading list");
  expect(wrapper.text()).toContain("Recently added");
  expect(wrapper.find('a[href="/gallery/g1"]').exists()).toBe(false);
  useRecentlyAddedKinds().recentlyAddedKinds.value = ["gallery"];
  await flushPromises();
  expect(wrapper.find('a[href="/gallery/g1"]').exists()).toBe(true);
  useRecentlyAddedKinds().recentlyAddedKinds.value = [];
  await flushPromises();
  expect(wrapper.text()).not.toContain("Recently added");
  useRecentlyAddedKinds().recentlyAddedKinds.value = ["manga"];
  await flushPromises();
});

it("renders dashboard content, retries a failure, and guides an empty library to settings", async () => {
  api.failNext("GET", "/api/dashboard");
  const { wrapper } = await renderView(LibraryHome);
  expect(wrapper.text()).toContain("Couldn't");
  await click(wrapper, "Try again");
  expect(wrapper.text()).toContain("Story s1");
  expect(wrapper.text()).toContain("Manga");
  expect(wrapper.text()).not.toContain("Empty");
  wrapper.unmount();
  api.db.series = [];
  const empty = await renderView(LibraryHome);
  expect(empty.wrapper.text()).toContain("library");
  expect(empty.wrapper.find('a[href="/settings"]').exists()).toBe(true);
});

it("persists library filters and presets, restores them, and cycles include/exclude tags", async () => {
  const { wrapper } = await renderView(LibraryView, {
    props: { libraryKey: "manga" },
    path: "/manga?view=compact",
    pattern: "/manga",
  });
  expect(useDensity().density.value).toBe("compact");
  await click(wrapper, "Filters");
  const panel = wrapper.getComponent(FilterPanel);
  await click(panel, "Action");
  await click(panel, "Action");
  await click(panel, "Action");
  await click(panel, "Action");
  await click(panel, "OR");
  await click(panel, "AND");
  for (const text of ["Safe", "Shonen", "ongoing", "Unread"]) {
    await click(panel, text);
    await click(panel, text);
    await click(panel, text);
  }
  await input(wrapper, '[aria-label="Search this library"]', " Story ");
  await input(wrapper, '[placeholder="e.g. Unread Seinen"]', "Weekend");
  await click(wrapper, "Save");
  const saved = JSON.parse(localStorage.getItem("lychee.presets") ?? "[]");
  expect(saved[0]).toMatchObject({
    name: "Weekend",
    query: " Story ",
    tags: { action: "include" },
    ratings: ["safe"],
    demographics: ["shonen"],
    statuses: ["ongoing"],
    readStates: ["unread"],
  });
  await click(wrapper, "Clear all");
  const preset = wrapper.findAll("span.badge").find((s) => s.text() === "Weekend")!;
  await preset.trigger("click");
  await flushPromises();
  const chips = wrapper.findAll("button.badge-primary");
  expect(chips).toHaveLength(6);
  for (const chip of chips) await chip.trigger("click");
  await input(wrapper, '[placeholder="e.g. Unread Seinen"]', "Weekend");
  await wrapper.get('[placeholder="e.g. Unread Seinen"]').trigger("keyup.enter");
  await flushPromises();
  expect(JSON.parse(localStorage.getItem("lychee.presets") ?? "[]")).toHaveLength(1);
  await wrapper.get('[aria-label="Delete preset"]').trigger("click");
  await click(wrapper, "Clear all filters");
  expect(JSON.parse(localStorage.getItem("lychee.presets") ?? "[]")).toEqual([]);
  await wrapper.get('[aria-label="Gallery view"]').trigger("click");
  expect(useDensity().density.value).toBe("gallery");
  await wrapper.get('[aria-label="List view"]').trigger("click");
  await wrapper.findAll("select")[0]!.setValue("Title");
  await click(wrapper, "Reading");
  await vi.waitFor(() =>
    expect(
      api.requests
        .filter((r) => r.path === "/api/series")
        .at(-1)
        ?.query.get("shelf"),
    ).toBe("reading"),
  );
  expect(
    api.requests
      .filter((r) => r.path === "/api/series")
      .at(-1)
      ?.query.get("sort"),
  ).toBe("title");
});

it("handles malformed presets and unknown library headings and retries failed grids", async () => {
  localStorage.setItem("lychee.presets", "broken");
  api.failNext("GET", "/api/series");
  const { wrapper } = await renderView(LibraryView, { props: { libraryKey: "unknown" } });
  expect(wrapper.get("h1").text()).toBe("Library");
  expect(wrapper.text()).toContain("Couldn't load this library");
  await click(wrapper, "Try again");
  expect(wrapper.text()).toContain("Story s1");
  wrapper.unmount();
  const reading = await renderView(LibraryView, { props: { libraryKey: "reading" } });
  expect(reading.wrapper.find("[role=tablist]").exists()).toBe(false);
});

it("filters galleries by artist, characters and franchise and sorts their titles", async () => {
  api.db.series.push(
    makeSeries("g2", {
      kind: "gallery",
      title: "Alternate",
      artists: ["Other"],
      source: "Elsewhere",
      characters: ["Guest"],
    }),
  );
  const { wrapper } = await renderView(GalleryView);
  expect(wrapper.text()).toContain("Gallery");
  const search = wrapper.get("input[type=search]");
  for (const term of ["Gallery", "model", "Hero", "Franchise", "missing"]) {
    await search.setValue(term);
    await flushPromises();
    expect(wrapper.text()).toContain(term === "missing" ? "No" : "Gallery");
  }
  await search.setValue("");
  const selects = wrapper.findAll("select");
  await selects[0]!.setValue("Model");
  await flushPromises();
  expect(wrapper.text()).not.toContain("Alternate");
  await selects[0]!.setValue("");
  await selects[1]!.setValue("Elsewhere");
  await flushPromises();
  expect(wrapper.text()).toContain("Alternate");
  await selects[1]!.setValue("");
  await selects[2]!.setValue("Title");
});

it("sorts the added feed, filters by recently added kinds, and switches its shared density", async () => {
  useRecentlyAddedKinds().recentlyAddedKinds.value = ["manga"];
  const { wrapper } = await renderView(AddedView);
  expect(wrapper.text()).toContain("Story s1");
  expect(wrapper.text()).not.toContain("Gallery g1");
  await input(wrapper, "select", "Title");
  await vi.waitFor(() =>
    expect(
      api.requests
        .filter((r) => r.path === "/api/series")
        .at(-1)
        ?.query.get("sort"),
    ).toBe("title"),
  );
  useRecentlyAddedKinds().recentlyAddedKinds.value = [];
  await flushPromises();
  expect(
    api.requests
      .filter((r) => r.path === "/api/series")
      .at(-1)
      ?.query.get("kind"),
  ).toBe("none");
  useRecentlyAddedKinds().recentlyAddedKinds.value = ["manga"];
  await wrapper.get('[aria-label="Compact view"]').trigger("click");
  expect(useDensity().density.value).toBe("compact");
});

it.each([true, false])(
  "renders the chapter feed unreadOnly=%s and changes density",
  async (unreadOnly) => {
    const { wrapper } = await renderView(ChapterFeedView, { props: { unreadOnly } });
    expect(
      api.requests.some((r) => r.path === (unreadOnly ? "/api/updates/unread" : "/api/updates")),
    ).toBe(true);
    expect(wrapper.text()).toContain("Story s1");
    await wrapper.get('[aria-label="List view"]').trigger("click");
    await wrapper.get('[aria-label="Thumbnail list view"]').trigger("click");
  },
);

it("filters reading lists by kind, creates a visible empty list and deletes it", async () => {
  useListsDefaultTab().listsDefaultTab.value = "manga";
  api.db.collections.push({ id: "mixed", name: "Mixed", kind: "mixed", seriesIds: ["s1", "g1"] });
  const { wrapper } = await renderView(ListsView);
  expect(wrapper.text()).toContain("Weekend");
  expect(wrapper.text()).not.toContain("Mixed");
  await click(wrapper, "Gallery");
  expect(wrapper.text()).toContain("No Gallery lists");
  await click(wrapper, "All");
  expect(wrapper.text()).toContain("Mixed");
  await click(wrapper, "New list");
  await input(wrapper, '[placeholder="List name…"]', " ");
  await wrapper.get("input").trigger("keyup.enter");
  expect(api.writes()).toHaveLength(0);
  await input(wrapper, '[placeholder="List name…"]', " My list ");
  await click(wrapper, "Create");
  expect(api.db.collections.at(-1)?.name).toBe("My list");
  expect(wrapper.text()).toContain("My list");
  await wrapper.findAll('[aria-label="Delete list"]').at(-1)!.trigger("click");
  await flushPromises();
  expect(wrapper.text()).not.toContain("My list");
  await click(wrapper, "New list");
  await click(wrapper, "Cancel");
  useListsDefaultTab().listsDefaultTab.value = "comic";
  await flushPromises();
  expect(wrapper.text()).toContain("No Comics lists");
});

it("loads, renames and removes works from a list, then confirms deleting the list", async () => {
  const { wrapper, router } = await renderView(ListDetailView, {
    path: "/lists/list",
    pattern: "/lists/:id",
  });
  expect(wrapper.text()).toContain("Weekend");
  await wrapper.get('[aria-label="Rename list"]').trigger("click");
  await input(wrapper, "input", " New title ");
  await click(wrapper, "Save");
  expect(api.db.collections[0]!.name).toBe("New title");
  await wrapper.get('[aria-label="Rename list"]').trigger("click");
  await input(wrapper, "input", " ");
  await wrapper.get("input").trigger("keyup.enter");
  await flushPromises();
  expect(api.db.collections[0]!.name).toBe("New title");
  await wrapper.get('[aria-label="Remove from list"]').trigger("click");
  await flushPromises();
  expect(wrapper.text()).toContain("No works");
  expect(api.db.collections[0]!.seriesIds).toEqual([]);
  await wrapper.get('[aria-label="Rename list"]').trigger("click");
  await click(wrapper, "Cancel");
  await click(wrapper, "Delete list");
  await wrapper.getComponent(ConfirmDialog).get('[aria-label="Close"]').trigger("click");
  await click(wrapper, "Delete list");
  await click(wrapper.getComponent(ConfirmDialog), "Delete list");
  expect(router.currentRoute.value.path).toBe("/lists");
  expect(api.db.collections).toEqual([]);
});

it("shows missing lists and empty list collections", async () => {
  const missing = await renderView(ListDetailView, {
    path: "/lists/missing",
    pattern: "/lists/:id",
  });
  expect(missing.wrapper.text()).toContain("List not found");
  missing.wrapper.unmount();
  api.db.collections = [];
  const empty = await renderView(ListsView);
  expect(empty.wrapper.text()).toContain("No lists yet");
});

it("ignores an older gallery response after navigating to another gallery", async () => {
  let release!: () => void;
  const waiting = new Promise<void>((resolve) => {
    release = resolve;
  });
  api.server.use(
    http.get("http://localhost/api/series/g1", async () => {
      await waiting;
      return HttpResponse.json(api.db.series[2]);
    }),
  );
  const { default: GalleryDetail } = await import("./GalleryDetail.vue");
  const { wrapper, router } = await renderView(GalleryDetail, {
    path: "/gallery/g1",
    pattern: "/gallery/:id",
  });
  await router.push("/gallery/s2");
  await flushPromises();
  expect(wrapper.get("h1").text()).toBe("Second story");
  release();
  await flushPromises();
  expect(wrapper.get("h1").text()).toBe("Second story");
});
