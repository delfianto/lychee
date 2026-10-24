import { flushPromises, mount } from "@vue/test-utils";
import { createPinia } from "pinia";
import { createMemoryHistory, createRouter, RouterView } from "vue-router";
import { http, HttpResponse } from "msw";
import { expect, it, vi } from "vite-plus/test";
import { useAppApi, makeSeries } from "../test/appApi";
import SeriesDetail from "./SeriesDetail.vue";
import GalleryDetail from "./GalleryDetail.vue";
import LibraryView from "./LibraryView.vue";
vi.mock("../api/client", async (original) => ({
  ...(await original<typeof import("../api/client")>()),
  api: (await import("../test/client")).testClient(),
}));
const api = useAppApi();

it.each(
  (["manga", "comic", "gallery"] as const).flatMap((kind) => [
    { kind, timing: "pending" },
    { kind, timing: "saved" },
  ]),
)(
  "refreshes cached $kind favorites when the edit is $timing during navigation",
  async ({ kind, timing }) => {
    const series = makeSeries("favorite", { kind, libraryStatus: "completed" });
    api.db.series = [series, makeSeries("other", { kind, favorite: false })];
    let release!: () => void;
    api.server.use(
      http.patch("http://localhost/api/series/favorite", async ({ request }) => {
        const body = (await request.json()) as { favorite: boolean };
        await new Promise<void>((resolve) => {
          release = resolve;
        });
        series.favorite = body.favorite;
        return HttpResponse.json(series);
      }),
    );
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: "/series/:id", component: SeriesDetail },
        { path: "/gallery/:id", component: GalleryDetail },
        { path: "/favorites", component: LibraryView, props: { libraryKey: "favorites" } },
      ],
    });
    await router.push("/favorites");
    await router.isReady();
    const wrapper = mount(
      {
        components: { RouterView },
        template:
          '<RouterView v-slot="{Component, route}"><KeepAlive include="LibraryView"><component :is="Component" :key="route.path" /></KeepAlive></RouterView>',
      },
      {
        attachTo: document.body,
        global: { plugins: [router, createPinia()] },
      },
    );
    await flushPromises();
    await router.push(kind === "gallery" ? "/gallery/favorite" : "/series/favorite");
    await flushPromises();
    await wrapper.get('[aria-label="Favorite"]').trigger("click");
    await flushPromises();
    if (timing === "saved") {
      release();
      await flushPromises();
    }
    await router.push("/favorites");
    await flushPromises();
    const link = kind === "gallery" ? "/gallery/favorite" : "/series/favorite";
    if (timing === "pending") {
      expect(wrapper.find(`a[href="${link}"]`).exists()).toBe(false);
      release();
      await flushPromises();
    }
    await vi.waitFor(() => expect(wrapper.find(`a[href="${link}"]`).exists()).toBe(true));
    expect(wrapper.find('a[href="/series/other"]').exists()).toBe(false);
    expect(wrapper.find('a[href="/gallery/other"]').exists()).toBe(false);
    const reads = api.requests.filter((request) => request.path === "/api/series").length;
    await router.push(kind === "gallery" ? "/gallery/favorite" : "/series/favorite");
    await flushPromises();
    await router.push("/favorites");
    await flushPromises();
    expect(api.requests.filter((request) => request.path === "/api/series")).toHaveLength(reads);
  },
);
