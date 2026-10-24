import { flushPromises } from "@vue/test-utils";
import { http, HttpResponse } from "msw";
import { expect, it, vi } from "vite-plus/test";
import { useAppApi, makeSeries, taskEvent } from "../test/appApi";
import { renderView, renderComponent, click, input } from "../test/views";
import SeriesDetail from "./SeriesDetail.vue";
import GalleryDetail from "./GalleryDetail.vue";
import EditSeriesModal from "../components/EditSeriesModal.vue";
import MatchSeriesModal from "../components/MatchSeriesModal.vue";
import ConfirmDialog from "../components/ConfirmDialog.vue";
import Lightbox from "../components/Lightbox.vue";
import { useToasts } from "../lib/toast";
vi.mock("../api/client", async (original) => ({
  ...(await original<typeof import("../api/client")>()),
  api: (await import("../test/client")).testClient(),
}));
vi.mock("plyr", async () => ({ default: (await import("../test/player")).TestPlayer }));
const api = useAppApi();
const messages = () =>
  useToasts()
    .value.map((t) => t.message)
    .join("\n");
async function link(wrapper: Awaited<ReturnType<typeof renderView>>["wrapper"], text: string) {
  const a = wrapper.findAll("a").find((a) => a.text().trim() === text);
  if (!a) throw new Error(`Missing link ${text}`);
  await a.trigger("click");
  await flushPromises();
}

it("loads series details, persists shelf/favorite/rating, and browses chapter filters and tabs", async () => {
  const { wrapper } = await renderView(SeriesDetail, {
    path: "/series/s1",
    pattern: "/series/:id",
  });
  expect(wrapper.get("h1").text()).toBe("Story s1");
  expect(wrapper.find('a[href="/read/adhoc:s1:remote-3"]').exists()).toBe(true);
  await wrapper.get('[aria-label="Favorite"]').trigger("click");
  await flushPromises();
  expect(api.writes().at(-1)?.body).toEqual({ favorite: true });
  await link(wrapper, "Completed");
  expect(api.writes().at(-1)?.body).toEqual({ libraryStatus: "completed" });
  const rating = wrapper.get('[aria-label="Rate 8 of 10"]');
  await rating.trigger("mouseenter");
  await rating.trigger("click");
  await flushPromises();
  expect(api.writes().at(-1)?.body).toEqual({ rating: 8 });
  await click(wrapper, "Clear rating");
  expect(api.writes().at(-1)?.body).toEqual({ rating: null });
  const expand = wrapper.findAll("button").find((b) => b.text().includes("more"));
  if (expand) await expand.trigger("click");
  await input(wrapper, '[aria-label="Filter by language"]', "en");
  expect(
    api.requests
      .filter((r) => r.path.endsWith("/chapters"))
      .at(-1)
      ?.query.get("language"),
  ).toBe("en");
  await click(wrapper, "Newest");
  expect(
    api.requests
      .filter((r) => r.path.endsWith("/chapters"))
      .at(-1)
      ?.query.get("order"),
  ).toBe("asc");
  await click(wrapper, "Related");
  expect(wrapper.text()).toContain("Second story");
  await click(wrapper, "Art");
  expect(wrapper.find('img[src="/art1"]').exists()).toBe(true);
  await click(wrapper, "Chapters");
  taskEvent("metadata");
  taskEvent("download");
  taskEvent("unrelated");
  await flushPromises();
  expect(wrapper.get("h1").text()).toBe("Story s1");
});

it("handles download failures, retries individual chapters, and reloads after confirmed deletion", async () => {
  const { wrapper } = await renderView(SeriesDetail, {
    path: "/series/s1",
    pattern: "/series/:id",
  });
  api.failNext("POST", "/api/downloads");
  await click(wrapper, "Download available");
  expect(messages()).toContain("Rejected by server");
  await click(wrapper, "Download available");
  expect(messages()).toContain("Downloading available chapters");
  api.failNext("POST", "/api/downloads");
  await wrapper.get('[aria-label="Download chapter"]').trigger("click");
  await flushPromises();
  expect(wrapper.get('[aria-label="Download chapter"]').attributes("disabled")).toBeUndefined();
  await wrapper.get('[aria-label="Download chapter"]').trigger("click");
  await flushPromises();
  expect(messages()).toContain("Chapter queued");
  const remove = wrapper.findAll('[aria-label^="Permanently delete chapter"]')[0]!;
  await remove.trigger("click");
  api.failNext("DELETE", "/api/chapters/2");
  await click(wrapper.getComponent(ConfirmDialog), "Delete permanently");
  expect(messages()).toContain("Rejected by server");
  await remove.trigger("click");
  await click(wrapper.getComponent(ConfirmDialog), "Delete permanently");
  expect(messages()).toContain("can be re-downloaded");
  api.server.use(
    http.delete("http://localhost/api/chapters/2", () =>
      HttpResponse.json({ mode: "local", redownloadable: false, seriesId: "s1" }),
    ),
  );
  await wrapper.findAll('[aria-label^="Permanently delete chapter"]')[0]!.trigger("click");
  await click(wrapper.getComponent(ConfirmDialog), "Delete permanently");
  expect(messages()).toContain("permanently deleted");
});

it("matches, refreshes and unlinks provider metadata and edits the series", async () => {
  const { wrapper } = await renderView(SeriesDetail, {
    path: "/series/s1",
    pattern: "/series/:id",
  });
  await link(wrapper, "Refresh metadata");
  expect(messages()).toContain("Refreshing metadata");
  await link(wrapper, "Match on MangaDex…");
  const match = wrapper.getComponent(MatchSeriesModal);
  await match.get('[aria-label="Search for a matching series"]').setValue(" ");
  await click(match, "Search");
  expect(
    api.requests
      .filter((r) => r.path.endsWith("match-candidates"))
      .at(-1)
      ?.query.has("q"),
  ).toBe(false);
  await match.findAll("li button")[1]!.trigger("click");
  await flushPromises();
  expect(wrapper.findComponent(MatchSeriesModal).exists()).toBe(false);
  expect(messages()).toContain("Matched");
  await link(wrapper, "Match on MangaDex…");
  await wrapper.getComponent(MatchSeriesModal).get('[aria-label="Close"]').trigger("click");
  await link(wrapper, "Unlink source");
  expect(api.db.series[0]!.provider).toBeNull();
  await click(wrapper, "Edit");
  const edit = wrapper.getComponent(EditSeriesModal);
  await edit.findAll("input")[0]!.setValue("Edited title");
  await click(edit, "Save");
  expect(wrapper.get("h1").text()).toBe("Edited title");
  await click(wrapper, "Edit");
  await click(wrapper.getComponent(EditSeriesModal), "Cancel");
  expect(wrapper.findComponent(EditSeriesModal).exists()).toBe(false);
});

it("retries missing detail requests and ignores stale route results", async () => {
  api.failNext("GET", "/api/series/s1");
  const { wrapper, router } = await renderView(SeriesDetail, {
    path: "/series/s1",
    pattern: "/series/:id",
  });
  expect(wrapper.text()).toContain("Couldn't");
  await click(wrapper, "Try again");
  expect(wrapper.get("h1").text()).toBe("Story s1");
  let release!: () => void;
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  api.server.use(
    http.get("http://localhost/api/series/s1", async () => {
      await pending;
      return HttpResponse.json(makeSeries());
    }),
  );
  await router.push("/series/s2");
  await flushPromises();
  await router.push("/series/s1");
  await flushPromises();
  await router.push("/series/s2");
  await flushPromises();
  release();
  await flushPromises();
  expect(wrapper.get("h1").text()).toBe("Second story");
});

it("uses gallery preview fallbacks and navigates the lightbox without changing the full page", async () => {
  const { wrapper } = await renderView(GalleryDetail, {
    path: "/gallery/g1",
    pattern: "/gallery/:id",
  });
  expect(wrapper.get("h1").text()).toBe("Gallery");
  expect(wrapper.get('[aria-label="Open image 1"] img').attributes("src")).toBe("/thumb");
  expect(wrapper.get('[aria-label="Open image 2"] img').attributes("src")).toBe("/poster");
  expect(wrapper.get('[aria-label="Play video 3"] img').attributes("src")).toBe("/video.mp4");
  await wrapper.get('[aria-label="Favorite"]').trigger("click");
  await flushPromises();
  expect(api.writes().at(-1)?.body).toEqual({ favorite: true });
  await click(wrapper, "View");
  expect(wrapper.getComponent(Lightbox).props("index")).toBe(0);
  await wrapper.getComponent(Lightbox).get('[aria-label="Next"]').trigger("click");
  expect(wrapper.getComponent(Lightbox).props("index")).toBe(1);
  await wrapper.getComponent(Lightbox).get('[aria-label="Close"]').trigger("click");
  await wrapper.get('[aria-label="Play video 3"]').trigger("click");
  await flushPromises();
  expect(wrapper.getComponent(Lightbox).find("video").exists()).toBe(true);
  await wrapper.getComponent(Lightbox).get('[aria-label="Close"]').trigger("click");
  await click(wrapper, "Edit");
  await click(wrapper.getComponent(EditSeriesModal), "Cancel");
  await click(wrapper, "Edit");
  await click(wrapper.getComponent(EditSeriesModal), "Save");
  expect(wrapper.findComponent(EditSeriesModal).exists()).toBe(false);
});

it("retries gallery failures and renders sparse gallery metadata", async () => {
  api.failNext("GET", "/api/series/g1");
  Object.assign(api.db.series[2]!, {
    year: undefined,
    description: undefined,
    artists: [],
    source: undefined,
    characters: [],
    tags: [],
  });
  api.db.images = [];
  const { wrapper } = await renderView(GalleryDetail, {
    path: "/gallery/g1",
    pattern: "/gallery/:id",
  });
  await click(wrapper, "Try again");
  expect(wrapper.get("h1").text()).toBe("Gallery");
  expect(
    wrapper
      .findAll("button")
      .find((b) => b.text() === "View")!
      .attributes("disabled"),
  ).toBeDefined();
});

it("edits book metadata using trimmed values, tags, people and nullable fields", async () => {
  const { wrapper } = await renderComponent(EditSeriesModal, { props: { series: makeSeries() } });
  await wrapper.findAll("input")[0]!.setValue(" Revised ");
  await input(wrapper, "input[type=number]", "");
  await input(wrapper, "textarea", " ");
  await input(wrapper, '[placeholder="Add author + Enter"]', "New writer");
  await wrapper.get('[placeholder="Add author + Enter"]').trigger("keyup.enter");
  await input(wrapper, '[placeholder="Add author + Enter"]', "New writer");
  await wrapper.get('[placeholder="Add author + Enter"]').trigger("keyup.enter");
  await input(wrapper, '[placeholder="Add + Enter"]', "New artist");
  await wrapper.get('[placeholder="Add + Enter"]').trigger("keyup.enter");
  await wrapper.findAll('[aria-label="Remove"]')[0]!.trigger("click");
  await click(wrapper, "Action");
  await click(wrapper, "Drama");
  const selects = wrapper.findAll("select");
  for (const [i, value] of [
    [0, ""],
    [1, "completed"],
    [2, "suggestive"],
    [3, "seinen"],
  ] as const)
    await selects[i]!.setValue(value);
  await click(wrapper, "Save");
  expect(api.writes().at(-1)?.body).toMatchObject({
    title: "Revised",
    description: null,
    year: null,
    authors: ["New writer"],
    artists: ["Artist", "New artist"],
    tagIds: ["drama"],
    originCountry: null,
    status: "completed",
    demographic: "seinen",
  });
});

it("rejects blank metadata titles and preserves gallery edits after a rejected save", async () => {
  const { wrapper } = await renderComponent(EditSeriesModal, {
    props: {
      series: makeSeries("g1", {
        kind: "gallery",
        authors: [],
        artists: [],
        characters: [],
        year: undefined,
        source: undefined,
      }),
    },
  });
  await wrapper.findAll("input")[0]!.setValue(" ");
  await click(wrapper, "Save");
  expect(api.writes()).toHaveLength(0);
  expect(messages()).toContain("Title can't be empty");
  await wrapper.findAll("input")[0]!.setValue("New gallery");
  await input(wrapper, '[placeholder="e.g. Genshin Impact"]', " Franchise ");
  await input(wrapper, '[placeholder="Add character + Enter"]', " Hero ");
  await wrapper.get('[placeholder="Add character + Enter"]').trigger("keyup.enter");
  await input(wrapper, "input[type=number]", "2025");
  api.failNext("PATCH", "/api/series/g1");
  await click(wrapper, "Save");
  expect(wrapper.emitted("saved")).toBeUndefined();
  expect(messages()).toContain("Couldn't save changes");
  await click(wrapper, "Save");
  expect(wrapper.emitted("saved")).toHaveLength(1);
  expect(api.writes().at(-1)?.body).toMatchObject({
    title: "New gallery",
    year: 2025,
    source: "Franchise",
    characters: ["Hero"],
  });
});

it("rolls rejected preference writes back instead of leaving false saved state", async () => {
  api.db.series[0]!.userRating = 7;
  const { wrapper } = await renderView(SeriesDetail, {
    path: "/series/s1",
    pattern: "/series/:id",
  });
  api.failNext("PATCH", "/api/series/s1");
  await wrapper.get('[aria-label="Favorite"]').trigger("click");
  await flushPromises();
  expect(wrapper.get('[aria-label="Favorite"]').classes()).not.toContain("text-error");
  api.failNext("PATCH", "/api/series/s1");
  await link(wrapper, "Completed");
  expect(wrapper.text()).toContain("Reading");
  expect(messages()).toContain("Couldn't save reading status");
  api.failNext("PATCH", "/api/series/s1");
  await wrapper.get('[aria-label="Rate 10 of 10"]').trigger("click");
  await flushPromises();
  expect(wrapper.text()).toContain("7/10");
  api.failNext("PATCH", "/api/series/s1");
  await click(wrapper, "Clear rating");
  expect(wrapper.text()).toContain("7/10");
  wrapper.unmount();
  const gallery = await renderView(GalleryDetail, { path: "/gallery/g1", pattern: "/gallery/:id" });
  api.failNext("PATCH", "/api/series/g1");
  await gallery.wrapper.get('[aria-label="Favorite"]').trigger("click");
  await flushPromises();
  expect(gallery.wrapper.get('[aria-label="Favorite"]').classes()).not.toContain("text-error");
});

it("keeps the latest rating when an older rejected write finishes afterward", async () => {
  api.db.series[0]!.userRating = 7;
  let release!: () => void;
  const waiting = new Promise<void>((resolve) => {
    release = resolve;
  });
  let started!: () => void;
  const entered = new Promise<void>((resolve) => {
    started = resolve;
  });
  api.server.use(
    http.patch(
      "http://localhost/api/series/s1",
      async () => {
        started();
        await waiting;
        return HttpResponse.json({ error: { message: "Older write rejected" } }, { status: 409 });
      },
      { once: true },
    ),
  );
  const { wrapper } = await renderView(SeriesDetail, {
    path: "/series/s1",
    pattern: "/series/:id",
  });
  await wrapper.get('[aria-label="Rate 8 of 10"]').trigger("click");
  await entered;
  await wrapper.get('[aria-label="Rate 9 of 10"]').trigger("click");
  await flushPromises();
  release();
  await flushPromises();
  expect(wrapper.text()).toContain("9/10");
});

it("retries an unsuccessful chapter check and shows an unnumbered readable chapter", async () => {
  let recovered = false;
  api.server.use(
    http.get("http://localhost/api/series/s1/chapters", () =>
      HttpResponse.json(
        recovered
          ? [
              {
                volume: null,
                chapters: [
                  {
                    id: null,
                    number: "Oneshot",
                    title: "Complete story",
                    language: "en",
                    read: false,
                    comments: 0,
                    status: "available",
                    providerChapterId: "oneshot",
                  },
                ],
              },
            ]
          : [],
      ),
    ),
    http.get("http://localhost/api/series/s1/chapter-availability", ({ request }) => {
      if (new URL(request.url).searchParams.get("refresh") === "true") recovered = true;
      return HttpResponse.json({
        status: recovered ? "ready" : "error",
        language: "en",
        availableLanguages: recovered ? ["en"] : [],
        availableCount: recovered ? 1 : 0,
        totalCount: recovered ? 1 : 0,
        sourceUrl: "https://mangadex.org/title/remote",
        message: recovered ? null : "Could not check chapters on MangaDex.",
      });
    }),
  );
  const { wrapper } = await renderView(SeriesDetail, {
    path: "/series/s1",
    pattern: "/series/:id",
  });
  expect(wrapper.text()).toContain("Could not check chapters on MangaDex");
  await click(wrapper, "Retry chapter check");
  await vi.waitFor(() => expect(wrapper.text()).toContain("Complete story"));
  expect(wrapper.text()).toContain("Oneshot");
  expect(wrapper.text()).not.toContain("Could not check chapters on MangaDex");
  expect(recovered).toBe(true);
});

it("discards a chapter-check retry response after navigating to another manga", async () => {
  let release: () => void = () => {};
  let requested = false;
  api.db.series.push(makeSeries("other", { title: "Other manga" }));
  api.server.use(
    http.get("http://localhost/api/series/s1/chapters", () => HttpResponse.json([])),
    http.get("http://localhost/api/series/s1/chapter-availability", async ({ request }) => {
      if (new URL(request.url).searchParams.get("refresh") === "true") {
        requested = true;
        await new Promise<void>((resolve) => {
          release = resolve;
        });
      }
      return HttpResponse.json({
        status: "error",
        language: "en",
        availableLanguages: [],
        availableCount: 0,
        totalCount: 0,
      });
    }),
  );
  const { wrapper, router } = await renderView(SeriesDetail, {
    path: "/series/s1",
    pattern: "/series/:id",
  });
  await click(wrapper, "Retry chapter check");
  await vi.waitFor(() => expect(requested).toBe(true));
  await router.push("/series/other");
  await flushPromises();
  release();
  await flushPromises();
  expect(wrapper.get("h1").text()).toBe("Other manga");
  expect(wrapper.text()).not.toContain("Could not check chapters on MangaDex");
});

it("marks individual and selected remote/local chapters read, retries failures, and clears read status", async () => {
  api.db.series[0]!.sourceUrl = "https://mangadex.org/title/md-title";
  api.db.series[0]!.authors = ["First writer", "Second writer"];
  api.db.chapters[0]!.chapters[0]!.sourceUrl = "https://mangadex.org/chapter/md-chapter";
  const { wrapper } = await renderView(SeriesDetail, {
    path: "/series/s1",
    pattern: "/series/:id",
  });
  expect(wrapper.findAll('a[href="/search?author=First+writer"]').length).toBeGreaterThan(0);
  expect(wrapper.get('a[href="https://mangadex.org/title/md-title"]').text()).toContain("MangaDex");
  expect(
    wrapper.get('a[href="https://mangadex.org/chapter/md-chapter"]').attributes("target"),
  ).toBe("_blank");
  const mark = wrapper
    .findAll('button[aria-label^="Mark chapter"]')
    .find((b) => b.attributes("aria-label")?.endsWith(" read"))!;
  api.failNext("PUT", "/api/series/s1/read-status");
  await mark.trigger("click");
  await flushPromises();
  expect(messages()).toContain("Rejected by server");
  expect(mark.attributes("disabled")).toBeUndefined();
  await mark.trigger("click");
  await flushPromises();
  expect(api.writes().at(-1)?.body).toMatchObject({ completed: true });
  await wrapper.get('[aria-label="Select all chapters"]').setValue(true);
  await click(wrapper, "Mark selected read");
  expect(api.db.chapters.flatMap((g) => g.chapters).every((c) => c.read)).toBe(true);
  expect(api.writes().at(-1)?.body.chapterIds).toContain("adhoc:s1:remote-3");
  await click(wrapper, "Mark all unread");
  expect(api.db.chapters.flatMap((g) => g.chapters).every((c) => !c.read)).toBe(true);
});

it("ignores a delayed read-status response after navigating to another series", async () => {
  let release!: () => void;
  api.server.use(
    http.put("http://localhost/api/series/s1/read-status", async () => {
      await new Promise<void>((resolve) => {
        release = resolve;
      });
      return HttpResponse.json({ updated: 1 });
    }),
  );
  const { wrapper, router } = await renderView(SeriesDetail, {
    path: "/series/s1",
    pattern: "/series/:id",
  });
  await wrapper.findAll('button[aria-label^="Mark chapter"]')[0]!.trigger("click");
  await flushPromises();
  await router.push("/series/s2");
  await flushPromises();
  release();
  await flushPromises();
  expect(wrapper.get("h1").text()).toBe("Second story");
});
