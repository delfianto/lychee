import { flushPromises } from "@vue/test-utils";
import { http, HttpResponse } from "msw";
import { expect, it, vi } from "vite-plus/test";
import { taskEvent, useAppApi } from "../test/appApi";
import { renderView, renderComponent, click, input } from "../test/views";
import { useToasts } from "../lib/toast";
import MangaDexListImport from "./MangaDexListImport.vue";
import MangaDexListActions from "./MangaDexListActions.vue";
import ChapterAvailabilityNotice from "./ChapterAvailabilityNotice.vue";
import ChapterList from "./ChapterList.vue";
import { useCollections } from "../stores/collections";
import { fetchChapterAvailability } from "../api/queries";
vi.mock("../api/client", async (original) => ({
  ...(await original<typeof import("../api/client")>()),
  api: (await import("../test/client")).testClient(),
}));
const api = useAppApi();
const messages = () =>
  useToasts()
    .value.map((t) => t.message)
    .join("\n");
const owned = {
  id: "md",
  name: "MDList",
  seriesIds: [],
  provider: "mangadex",
  providerListId: "remote",
  sourceUrl: "https://mangadex.org/list/remote",
  owned: true,
  followed: false,
  editable: true,
  visibility: "private" as const,
  lastSyncedAt: "2026-10-24T00:00:00Z",
};
function task() {
  return HttpResponse.json({
    id: "md-task",
    kind: "mdlist",
    label: "MDList",
    status: "running",
    progress: 0,
  });
}

it("imports URLs, browses user lists, and follows background completion without losing errors", async () => {
  api.server.use(
    http.post("http://localhost/api/collections/mangadex/import", task),
    http.get("http://localhost/api/collections/mangadex/users/user/lists", () =>
      HttpResponse.json([
        {
          id: "remote",
          name: "Public MDList",
          visibility: "public",
          mangaCount: 3,
          sourceUrl: "https://mangadex.org/list/remote",
        },
      ]),
    ),
  );
  const { wrapper, router } = await renderView(MangaDexListImport);
  await click(wrapper, "Import or browse");
  await input(wrapper, '[aria-label="MangaDex URL or UUID"]', "https://mangadex.org/list/remote");
  api.failNext("POST", "/api/collections/mangadex/import");
  await click(wrapper, "Import");
  expect(messages()).toContain("Rejected by server");
  await click(wrapper, "Import");
  expect(wrapper.text()).toContain("Working in the background");
  taskEvent("mdlist", "failed", { id: "md-task", detail: "Import failed upstream" });
  await flushPromises();
  expect(messages()).toContain("Import failed upstream");
  await input(wrapper, "select", "user");
  await input(wrapper, "input", "https://mangadex.org/user/user/name");
  await click(wrapper, "Browse");
  expect(wrapper.text()).toContain("Public MDList");
  await click(wrapper, "Import list");
  taskEvent("mdlist", "done", { id: "md-task", result: { collectionId: "imported" } });
  await flushPromises();
  expect(router.currentRoute.value.path).toBe("/lists/imported");
});

it("queues account list sync and reports completion", async () => {
  api.server.use(http.post("http://localhost/api/collections/mangadex/sync", task));
  const { wrapper } = await renderView(MangaDexListImport);
  await click(wrapper, "Sync my lists and followed lists");
  taskEvent("mdlist", "done", { id: "md-task", result: { lists: 2 } });
  await flushPromises();
  expect(messages()).toContain("MangaDex lists synced");
});

it("edits owned list visibility, waits for sync, and reports sync errors", async () => {
  api.server.use(
    http.patch("http://localhost/api/collections/md", () => HttpResponse.json(owned)),
    http.post("http://localhost/api/collections/md/sync", task),
  );
  const { wrapper } = await renderComponent(MangaDexListActions, { props: { collection: owned } });
  expect(wrapper.text()).toContain("Your list");
  expect(wrapper.get("a").attributes("href")).toBe(owned.sourceUrl);
  await input(wrapper, "select", "public");
  expect(messages()).toContain("Visibility updated");
  await click(wrapper, "Sync list");
  taskEvent("mdlist", "failed", { id: "md-task", detail: "Sync failed upstream" });
  await flushPromises();
  expect(messages()).toContain("Sync failed upstream");
  await click(wrapper, "Sync list");
  taskEvent("mdlist", "done", { id: "md-task", result: { collectionId: "md" } });
  await flushPromises();
  expect(messages()).toContain("List synced");
});

it("follows read-only lists and reads paginated chapter updates with language filtering", async () => {
  let seenLanguage: string | null = null;
  const item = {
    chapterId: "c1",
    mangaId: "m1",
    mangaTitle: "Readable manga",
    seriesId: "s1",
    number: "1",
    title: "Start",
    language: "en",
    group: "Group",
    uploadedAt: "2026-10-24T00:00:00Z",
    sourceUrl: "https://mangadex.org/chapter/c1",
  };
  api.server.use(
    http.put("http://localhost/api/collections/md/follow", () =>
      HttpResponse.json({ ...owned, followed: true }),
    ),
    http.get("http://localhost/api/collections/md/feed", ({ request }) => {
      seenLanguage = new URL(request.url).searchParams.get("language");
      const page = Number(new URL(request.url).searchParams.get("page"));
      return HttpResponse.json({
        items: [
          {
            ...item,
            chapterId: `c${page}`,
            seriesId: page === 1 ? "s1" : null,
            number: page === 1 ? "1" : null,
          },
        ],
        total: 31,
        page,
        pageSize: 30,
      });
    }),
  );
  const readOnly = { ...owned, owned: false, editable: false, followed: false };
  const { wrapper } = await renderComponent(MangaDexListActions, {
    props: { collection: readOnly },
  });
  expect(wrapper.text()).toContain("Imported list · read-only");
  expect(wrapper.find("select").exists()).toBe(false);
  await click(wrapper, "Follow on MangaDex");
  expect(messages()).toContain("Following list");
  const component = wrapper;
  await component.setProps({ collection: { ...readOnly, followed: true } });
  await click(wrapper, "Unfollow on MangaDex");
  expect(messages()).toContain("Unfollowed list");
  const details = wrapper.get("details");
  (details.element as HTMLDetailsElement).open = true;
  await details.trigger("toggle");
  await flushPromises();
  expect(wrapper.text()).toContain("Readable manga");
  expect(wrapper.find('a[href="/series/s1"]').exists()).toBe(true);
  await click(wrapper, "Load more updates");
  expect(wrapper.text()).toContain("Oneshot");
  await input(wrapper, '[aria-label="List feed language"]', "ja");
  await wrapper.get("form").trigger("submit");
  await flushPromises();
  expect(seenLanguage).toBe("ja");
  api.failNext("GET", "/api/collections/md/feed");
  await click(wrapper, "Refresh updates");
  expect(wrapper.get('[role="alert"]').text()).toContain("Rejected by server");
});

it("keeps list state unchanged when upstream writes fail", async () => {
  const store = useCollections();
  await flushPromises();
  const list = store.lists[0]!;
  const name = list.name;
  api.failNext("PATCH", `/api/collections/${list.id}`);
  await expect(store.renameList(list.id, "Broken")).rejects.toThrow("Rejected by server");
  expect(list.name).toBe(name);
  api.failNext("POST", "/api/collections");
  await expect(store.createList("Broken")).rejects.toThrow("Rejected by server");
  api.failNext("DELETE", `/api/collections/${list.id}`);
  await expect(store.deleteList(list.id)).rejects.toThrow("Rejected by server");
  expect(store.getList(list.id)).toBeDefined();
  const sid = list.seriesIds[0]!;
  api.failNext("DELETE", `/api/collections/${list.id}/series/${sid}`);
  await expect(store.removeSeries(list.id, sid)).rejects.toThrow("Rejected by server");
  expect(list.seriesIds).toContain(sid);
  api.failNext("DELETE", `/api/collections/${list.id}/series/${sid}`);
  await expect(store.toggleSeries(list.id, sid)).rejects.toThrow("Rejected by server");
  api.failNext("POST", `/api/collections/${list.id}/series`);
  await expect(store.toggleSeries(list.id, "new")).rejects.toThrow("Rejected by server");
  expect(list.seriesIds).not.toContain("new");
});

it.each([
  ["error", "Could not check chapters"],
  ["language_unavailable", "other languages"],
  ["unavailable", "none are currently readable"],
  ["external_only", "external publisher"],
  ["no_chapters", "in any language"],
  ["not_checked", "not been checked"],
  ["local", "No chapters in the library"],
  ["ready", "No chapters match"],
])("explains chapter availability state %s", async (status, text) => {
  const { wrapper } = await renderView(ChapterAvailabilityNotice, {
    props: {
      availability: {
        status,
        language: "en",
        availableLanguages: ["fr"],
        availableCount: 0,
        totalCount: 0,
        checkedAt: "2026-10-24T00:00:00Z",
        sourceUrl: "https://mangadex.org/title/m1",
      },
    },
  });
  expect(wrapper.text()).toContain(text);
  if (status !== "local") {
    await wrapper.findAll("button")[0]!.trigger("click");
    expect(wrapper.getComponent(ChapterAvailabilityNotice).emitted("retry")).toHaveLength(1);
  }
});

it("renders oneshots and selectable available languages, and handles chapter-status transport failures", async () => {
  const { wrapper } = await renderView(ChapterList, {
    props: {
      volumes: [
        {
          volume: null,
          chapters: [
            {
              id: null,
              number: "Oneshot",
              language: "en",
              read: false,
              comments: 0,
              status: "available",
              providerChapterId: "c1",
            },
          ],
        },
      ],
      availability: {
        status: "ready",
        language: "en",
        availableLanguages: ["en", "fr"],
        availableCount: 1,
        totalCount: 1,
      },
    },
  });
  expect(wrapper.text()).toContain("Oneshot");
  expect(wrapper.find('option[value="fr"]').exists()).toBe(true);
  api.failNext("GET", "/api/series/s1/chapter-availability");
  expect((await fetchChapterAvailability("s1")).status).toBe("error");
});
