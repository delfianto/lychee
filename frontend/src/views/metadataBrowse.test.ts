import { flushPromises, mount } from "@vue/test-utils";
import { createPinia } from "pinia";
import { createMemoryHistory, createRouter, RouterView } from "vue-router";
import { expect, it, vi } from "vite-plus/test";
import { makeSeries, useAppApi } from "../test/appApi";
import { click, input, renderView } from "../test/views";
import SeriesInfoPanel from "../components/SeriesInfoPanel.vue";
import LibraryView from "./LibraryView.vue";
import SeriesDetail from "./SeriesDetail.vue";

vi.mock("../api/client", async (original) => ({
  ...(await original<typeof import("../api/client")>()),
  api: (await import("../test/client")).testClient(),
}));
const api = useAppApi();
const lastQuery = () => api.requests.filter((r) => r.path === "/api/series").at(-1)?.query;

async function browse(path: string) {
  api.db.series[0] = makeSeries("s1", {
    demographic: "josei",
    contentRating: "suggestive",
    status: "completed",
    tags: [{ id: "action", name: "Renamed Action", group: "genre" }],
  });
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/series/:id", component: SeriesDetail },
      { path: "/manga", component: LibraryView, props: { libraryKey: "manga" } },
      { path: "/comics", component: LibraryView, props: { libraryKey: "comics" } },
      { path: "/:pathMatch(.*)*", component: { template: "<div>Destination</div>" } },
    ],
  });
  await router.push(path);
  await router.isReady();
  const wrapper = mount(
    {
      components: { RouterView },
      template: `<RouterView v-slot="{ Component }"><KeepAlive include="LibraryView"><component :is="Component" :key="$route.path" /></KeepAlive></RouterView>`,
    },
    { attachTo: document.body, global: { plugins: [router, createPinia()] } },
  );
  await flushPromises();
  return { wrapper, router };
}

it.each([
  ["Josei", "demographics", "josei"],
  ["Suggestive", "ratings", "suggestive"],
  ["Completed", "pubStatus", "completed"],
  ["Renamed Action", "tags", "action"],
])(
  "browses %s directly from a work's sidebar using stable filter IDs",
  async (label, key, value) => {
    const { wrapper, router } = await browse("/series/s1");
    const link = wrapper
      .getComponent(SeriesInfoPanel)
      .findAll("a")
      .find((a) => a.text() === label)!;
    expect(link.attributes("href")).toBe(`/manga?${key}=${value}`);
    await link.trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.path).toBe("/manga");
    expect(lastQuery()?.get("kind")).toBe("manga");
    expect(lastQuery()?.get(key)).toBe(value);
    expect(wrapper.findAll("button.badge-primary")).toHaveLength(1);
    if (key === "tags") expect(lastQuery()?.get("tagMode")).toBe("and");

    await wrapper.get("button.badge-primary").trigger("click");
    await vi.waitFor(() => expect(lastQuery()?.has(key)).toBe(false));
  },
);

it("keeps comic metadata links inside the comic library, including the hero badges", async () => {
  const { wrapper, router } = await browse("/series/s1");
  api.db.series[0]!.kind = "comic";
  await router.push("/series/s2");
  await flushPromises();
  await router.push("/series/s1");
  await flushPromises();
  const sidebar = wrapper.getComponent(SeriesInfoPanel);
  for (const href of [
    "/comics?demographics=josei",
    "/comics?ratings=suggestive",
    "/comics?pubStatus=completed",
    "/comics?tags=action",
  ]) {
    expect(sidebar.find(`a[href="${href}"]`).exists()).toBe(true);
  }
  expect(wrapper.findAll('a[href="/comics?ratings=suggestive"]')).toHaveLength(2);
  expect(wrapper.findAll('a[href="/comics?pubStatus=completed"]')).toHaveLength(2);
  await sidebar.get('a[href="/comics?demographics=josei"]').trigger("click");
  await flushPromises();
  expect(router.currentRoute.value.path).toBe("/comics");
  expect(lastQuery()?.get("kind")).toBe("comic");
  expect(lastQuery()?.get("demographics")).toBe("josei");
});

it("replaces stale cached filters on a new metadata link and preserves edits on return", async () => {
  const { wrapper, router } = await browse("/manga?tags=action");
  await input(wrapper, '[aria-label="Search this library"]', "unrelated");
  await click(wrapper, "Reading");
  await vi.waitFor(() => expect(lastQuery()?.get("q")).toBe("unrelated"));
  await router.push("/series/s1");
  await flushPromises();
  await wrapper
    .getComponent(SeriesInfoPanel)
    .get('a[href="/manga?demographics=josei"]')
    .trigger("click");
  await flushPromises();
  await vi.waitFor(() => expect(lastQuery()?.get("demographics")).toBe("josei"));
  expect(lastQuery()?.has("tags")).toBe(false);
  expect(lastQuery()?.has("shelf")).toBe(false);
  expect(lastQuery()?.has("q")).toBe(false);
  expect(wrapper.get<HTMLInputElement>('[aria-label="Search this library"]').element.value).toBe(
    "",
  );
  expect(wrapper.findAll("button.badge-primary").map((chip) => chip.text())).toContain("Josei");

  await input(wrapper, '[aria-label="Search this library"]', "Story");
  await vi.waitFor(() => expect(lastQuery()?.get("q")).toBe("Story"));
  await router.push("/series/s1");
  await flushPromises();
  router.back();
  await vi.waitFor(() => expect(router.currentRoute.value.path).toBe("/manga"));
  await flushPromises();
  expect(wrapper.get<HTMLInputElement>('[aria-label="Search this library"]').element.value).toBe(
    "Story",
  );
  expect(wrapper.findAll("button.badge-primary").map((chip) => chip.text())).toContain("Josei");

  await router.push("/manga?ratings=safe");
  await flushPromises();
  await vi.waitFor(() => expect(lastQuery()?.get("ratings")).toBe("safe"));
  expect(lastQuery()?.has("demographics")).toBe(false);
  expect(lastQuery()?.has("q")).toBe(false);
  await router.push("/manga");
  await flushPromises();
  await vi.waitFor(() => expect(lastQuery()?.has("ratings")).toBe(false));
  expect(wrapper.findAll("button.badge-primary")).toHaveLength(0);
});

it("accepts repeated and comma-separated metadata filters and ignores invalid enum values", async () => {
  const { wrapper } = await renderView(LibraryView, {
    path: "/manga?ratings=safe,invalid&ratings=suggestive&ratings&demographics=josei,unknown&pubStatus=completed,typo&tags=action,-drama,-&tags",
    pattern: "/manga",
    props: { libraryKey: "manga" },
  });
  expect(lastQuery()?.get("ratings")).toBe("safe,suggestive");
  expect(lastQuery()?.get("demographics")).toBe("josei");
  expect(lastQuery()?.get("pubStatus")).toBe("completed");
  expect(lastQuery()?.get("tags")).toBe("action,-drama");
  expect(wrapper.findAll("button.badge-primary")).toHaveLength(6);
});
