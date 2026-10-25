import { flushPromises, mount } from "@vue/test-utils";
import { createPinia } from "pinia";
import { createMemoryHistory, createRouter, RouterView } from "vue-router";
import { http, HttpResponse } from "msw";
import { expect, it, vi } from "vite-plus/test";
import { makeSeries, taskEvent, useAppApi } from "../test/appApi";
import { click, input, renderView } from "../test/views";
import type { HomeSeries, RecentUpdate } from "../types";
import type { HomeSection } from "../stores/home";
import LibraryHome from "./LibraryHome.vue";
import LibraryView from "./LibraryView.vue";
import ListDetailView from "./ListDetailView.vue";

vi.mock("../api/client", async (original) => ({
  ...(await original<typeof import("../api/client")>()),
  api: (await import("../test/client")).testClient(),
}));
const api = useAppApi();
const preset = {
  name: "Weekend",
  query: "",
  tags: { action: "include" },
  tagMode: "and",
  ratings: ["safe"],
  demographics: ["josei"],
  statuses: [],
  readStates: [],
  author: "",
  artist: "",
};
function homeApi() {
  const works = (prefix: string, count: number): HomeSeries[] =>
    Array.from({ length: count }, (_, i) => ({
      ...makeSeries(`${prefix}-${i}`),
      resumeChapterId: `chapter-${i}`,
      resumeChapterLabel: String(i + 1),
    }));
  const data: Record<Exclude<HomeSection, "recentUpdates">, HomeSeries[]> = {
    continueReading: works("Continue", 53),
    readingList: works("Reading", 53),
    recentlyAdded: works("Added", 33),
    rediscover: [
      ...works("Forgotten", 30).map((s) => ({ ...s, chapterCount: 0, unreadCount: 0 })),
      { ...makeSeries("Comic forgotten"), kind: "comic" },
    ],
    quickReads: [
      { ...makeSeries("Short"), pageCount: 42, chapterCount: 1 },
      { ...makeSeries("Short comic"), kind: "comic", pageCount: 60 },
    ],
  };
  const updates: RecentUpdate[] = works("Update", 51).map((series, i) => ({
    series,
    volume: null,
    chapter: String(i + 1),
    updatedAt: "2026-10-01T00:00:00Z",
  }));
  const queries: { path: string; query: URLSearchParams }[] = [];
  function page(section: HomeSection, url: URL) {
    const limit = Number(url.searchParams.get("limit") ?? 24),
      start = Number(url.searchParams.get("cursor") ?? 0);
    let items = section === "recentUpdates" ? [] : data[section];
    if (section === "rediscover" || section === "quickReads")
      items = items.filter((s) => s.kind === (url.searchParams.get("discoveryKind") ?? "manga"));
    const rows = section === "recentUpdates" ? updates : items;
    return {
      items: items.slice(start, start + limit),
      updates: section === "recentUpdates" ? updates.slice(start, start + limit) : [],
      nextCursor: start + limit < rows.length ? String(start + limit) : null,
    };
  }
  function dashboard(url: URL) {
    const names: HomeSection[] = [
      "continueReading",
      "readingList",
      "recentUpdates",
      "recentlyAdded",
      "rediscover",
      "quickReads",
    ];
    return {
      stats: { series: 200, unreadChapters: 120, reading: 53 },
      ...Object.fromEntries(
        names.map((name) => [
          name,
          name === "recentUpdates" ? page(name, url).updates : page(name, url).items,
        ]),
      ),
      cursors: Object.fromEntries(names.map((name) => [name, page(name, url).nextCursor])),
    };
  }
  api.server.use(
    http.get("http://localhost/api/dashboard", ({ request }) => {
      const url = new URL(request.url);
      queries.push({ path: url.pathname, query: url.searchParams });
      return HttpResponse.json(dashboard(url));
    }),
    http.get("http://localhost/api/dashboard/:section", ({ request, params }) => {
      const url = new URL(request.url);
      queries.push({ path: url.pathname, query: url.searchParams });
      return HttpResponse.json(page(String(params.section) as HomeSection, url));
    }),
  );
  return { data, queries, dashboard };
}
const shelf = (wrapper: Awaited<ReturnType<typeof renderView>>["wrapper"], id: string) =>
  wrapper.get(`[data-home-section="${id}"]`);

it("shows many resume cards with separate work links and paginates each existing shelf", async () => {
  const { queries } = homeApi();
  const { wrapper } = await renderView(LibraryHome);
  expect(shelf(wrapper, "continueReading").findAll('a[href^="/series/"]')).toHaveLength(24);
  expect(shelf(wrapper, "continueReading").get('a[href="/read/chapter-0"]').text()).toBe(
    "Continue",
  );
  for (const [id, title] of [
    ["continueReading", "Continue reading"],
    ["readingList", "On your reading list"],
    ["recentUpdates", "Recent updates"],
  ]) {
    await shelf(wrapper, id!).get(`[aria-label="Load more ${title}"]`).trigger("click");
    await vi.waitFor(() => expect(shelf(wrapper, id!).text()).toContain("48+"));
  }
  expect(shelf(wrapper, "continueReading").findAll('a[href^="/series/"]')).toHaveLength(48);
  expect(
    queries
      .filter((q) => q.path.startsWith("/api/dashboard/"))
      .every((q) => q.query.get("cursor") === "24"),
  ).toBe(true);
  expect(shelf(wrapper, "quickReads").text()).toContain("42 pages");
  expect(wrapper.text()).toContain("Not downloaded"); // source availability remains explicit
  await shelf(wrapper, "rediscover")
    .get('[aria-label="Shuffle Rediscover your library"]')
    .trigger("click");
  await vi.waitFor(() => expect(wrapper.find("[data-browse-loading]").exists()).toBe(false));
  expect(shelf(wrapper, "continueReading").findAll('a[href^="/series/"]')).toHaveLength(48);
});

it("keeps loaded cards on a paging error and retries without duplicating them", async () => {
  homeApi();
  const { wrapper } = await renderView(LibraryHome);
  api.failNext("GET", "/api/dashboard/readingList");
  await shelf(wrapper, "readingList")
    .get('[aria-label="Load more On your reading list"]')
    .trigger("click");
  await vi.waitFor(() =>
    expect(shelf(wrapper, "readingList").text()).toContain("Rejected by server"),
  );
  expect(shelf(wrapper, "readingList").findAll('a[href^="/series/"]')).toHaveLength(24);
  await click(shelf(wrapper, "readingList"), "Try again");
  await vi.waitFor(() =>
    expect(shelf(wrapper, "readingList").findAll('a[href^="/series/"]')).toHaveLength(48),
  );
  await shelf(wrapper, "readingList")
    .get('[aria-label="Load more On your reading list"]')
    .trigger("click");
  await vi.waitFor(() =>
    expect(shelf(wrapper, "readingList").findAll('a[href^="/series/"]')).toHaveLength(53),
  );
  expect(shelf(wrapper, "readingList").find('[aria-label^="Load more"]').exists()).toBe(false);
});

it("persists shelf visibility/order and discovery preferences, and ignores stale shuffle responses", async () => {
  const fixture = homeApi();
  const { wrapper } = await renderView(LibraryHome);
  await click(wrapper, "Customize Home");
  await wrapper.get('[aria-label="Show On your reading list"]').setValue(false);
  expect(wrapper.find('[data-home-section="readingList"]').exists()).toBe(false);
  await wrapper.get('[aria-label="Move Quick reads up"]').trigger("click");
  expect(
    wrapper
      .findAll("section[data-home-section]")
      .map((s) => s.attributes("data-home-section"))
      .indexOf("quickReads"),
  ).toBeLessThan(
    wrapper
      .findAll("section[data-home-section]")
      .map((s) => s.attributes("data-home-section"))
      .indexOf("rediscover"),
  );
  await flushPromises();
  expect(JSON.parse(localStorage.getItem("lychee.home")!).hidden).toContain("readingList");
  let release!: (response: Response) => void;
  let requested = false;
  api.server.use(
    http.get("http://localhost/api/dashboard", ({ request }) => {
      const url = new URL(request.url);
      if (url.searchParams.get("discoveryKind") === "manga" && !requested) {
        requested = true;
        return new Promise<Response>((resolve) => {
          release = resolve;
        });
      }
      return HttpResponse.json(fixture.dashboard(url));
    }),
  );
  await shelf(wrapper, "rediscover")
    .get('[aria-label="Shuffle Rediscover your library"]')
    .trigger("click");
  await vi.waitFor(() => expect(requested).toBe(true));
  await input(wrapper, '[aria-label="Discovery library"]', "comic");
  await vi.waitFor(() => expect(shelf(wrapper, "rediscover").text()).toContain("Comic forgotten"));
  release(
    HttpResponse.json(
      fixture.dashboard(new URL("http://localhost/api/dashboard?discoveryKind=manga")),
    ),
  );
  await flushPromises();
  expect(shelf(wrapper, "rediscover").text()).toContain("Comic forgotten");
  await click(wrapper, "Reset Home");
  await flushPromises();
});

it("pins a list and an editable saved filter, restores their routes, and unpins removed filters", async () => {
  const list = await renderView(ListDetailView, { path: "/lists/list", pattern: "/lists/:id" });
  await click(list.wrapper, "Show on Home");
  await flushPromises();
  expect(list.wrapper.get('[aria-pressed="true"]').text()).toContain("Pinned to Home");
  list.wrapper.unmount();
  localStorage.setItem("lychee.presets", JSON.stringify([preset]));
  const library = await renderView(LibraryView, { path: "/manga", props: { libraryKey: "manga" } });
  await library.wrapper.get('[aria-label="Pin Weekend to Home"]').trigger("click");
  await flushPromises();
  library.wrapper.unmount();
  homeApi();
  const { wrapper } = await renderView(LibraryHome);
  await vi.waitFor(() =>
    expect(wrapper.find('[data-home-section="list:list"]').exists()).toBe(true),
  );
  await vi.waitFor(() =>
    expect(shelf(wrapper, "list:list").findAll('a[href^="/series/"]')).toHaveLength(1),
  );
  expect(shelf(wrapper, "list:list").get("h2 a").attributes("href")).toBe("/lists/list");
  expect(shelf(wrapper, "filter:manga:Weekend").get("h2 a").attributes("href")).toBe(
    "/manga?preset=Weekend",
  );
  expect(
    api.requests.some((r) => r.path === "/api/series" && r.query.get("demographics") === "josei"),
  ).toBe(true);
  await click(wrapper, "Customize Home");
  await wrapper.get('[aria-label="Unpin Weekend filter"]').trigger("click");
  await flushPromises();
  expect(wrapper.find('[data-home-section="filter:manga:Weekend"]').exists()).toBe(false);
  wrapper.unmount();
  const linked = await renderView(LibraryView, {
    path: "/manga?preset=Weekend",
    pattern: "/manga",
    props: { libraryKey: "manga" },
  });
  expect(linked.wrapper.findAll("button.badge-primary").map((c) => c.text())).toContain("Josei");
});

it("keeps a failed pin isolated, retries it, and explains a deleted preset", async () => {
  localStorage.setItem(
    "lychee.home",
    JSON.stringify({
      pins: [
        { id: "list:list", type: "list", collectionId: "list" },
        { id: "filter:manga:Missing", type: "filter", name: "Missing", libraryKey: "manga" },
      ],
    }),
  );
  homeApi();
  api.failNext("GET", "/api/series");
  const { wrapper } = await renderView(LibraryHome);
  await vi.waitFor(() =>
    expect(shelf(wrapper, "list:list").text()).toContain("Rejected by server"),
  );
  expect(shelf(wrapper, "readingList").text()).toContain("Reading-0");
  expect(shelf(wrapper, "filter:manga:Missing").text()).toContain("saved filter was removed");
  await click(shelf(wrapper, "list:list"), "Try again");
  await vi.waitFor(() => expect(shelf(wrapper, "list:list").text()).toContain("Story s1"));
});

it("preserves loaded depth on return and does not refresh Home for offscreen download events", async () => {
  const fixture = homeApi();
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/", component: LibraryHome },
      { path: "/series/:id", component: { template: "<p>Work details</p>" } },
    ],
  });
  await router.push("/");
  await router.isReady();
  const wrapper = mount(
    {
      components: { RouterView },
      template:
        '<RouterView v-slot="{Component}"><KeepAlive include="LibraryHome"><component :is="Component" /></KeepAlive></RouterView>',
    },
    { attachTo: document.body, global: { plugins: [router, createPinia()] } },
  );
  await flushPromises();
  await shelf(wrapper, "readingList")
    .get('[aria-label="Load more On your reading list"]')
    .trigger("click");
  await vi.waitFor(() =>
    expect(shelf(wrapper, "readingList").findAll('a[href^="/series/"]')).toHaveLength(48),
  );
  await router.push("/series/s1");
  await flushPromises();
  const before = fixture.queries.filter((q) => q.path === "/api/dashboard").length;
  taskEvent("download");
  taskEvent("download");
  taskEvent("scan");
  await new Promise((resolve) => setTimeout(resolve, 300));
  expect(fixture.queries.filter((q) => q.path === "/api/dashboard")).toHaveLength(before);
  router.back();
  await vi.waitFor(() => expect(router.currentRoute.value.path).toBe("/"));
  await vi.waitFor(() =>
    expect(fixture.queries.filter((q) => q.path === "/api/dashboard")).toHaveLength(before + 1),
  );
  await vi.waitFor(() =>
    expect(shelf(wrapper, "readingList").findAll('a[href^="/series/"]')).toHaveLength(48),
  );
  taskEvent("metadata");
  taskEvent("download");
  await vi.waitFor(() =>
    expect(fixture.queries.filter((q) => q.path === "/api/dashboard")).toHaveLength(before + 2),
  );
});

it("loads later pages of a pinned list with its collection scope intact", async () => {
  localStorage.setItem(
    "lychee.home",
    JSON.stringify({ pins: [{ id: "list:list", type: "list", collectionId: "list" }] }),
  );
  homeApi();
  const cursors: (string | null)[] = [];
  api.server.use(
    http.get("http://localhost/api/series", ({ request }) => {
      const params = new URL(request.url).searchParams;
      expect(params.get("collectionId")).toBe("list");
      const cursor = params.get("cursor");
      cursors.push(cursor);
      return HttpResponse.json({
        items: [makeSeries(cursor ? "later" : "first")],
        nextCursor: cursor ? null : "next",
      });
    }),
  );
  const { wrapper } = await renderView(LibraryHome);
  await vi.waitFor(() => expect(shelf(wrapper, "list:list").text()).toContain("Story first"));
  await shelf(wrapper, "list:list").get('[aria-label="Load more Weekend"]').trigger("click");
  await vi.waitFor(() => expect(shelf(wrapper, "list:list").text()).toContain("Story later"));
  expect(shelf(wrapper, "list:list").text()).toContain("Story first");
  expect(cursors).toEqual([null, "next"]);
});
