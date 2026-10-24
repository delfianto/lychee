import { flushPromises } from "@vue/test-utils";
import { expect, it, vi } from "vite-plus/test";
import { useAppApi, makeTax, makeDownload, taskEvent } from "../../test/appApi";
import { renderView, click, input, button } from "../../test/views";
import { useToasts } from "../../lib/toast";
import ContentPanel from "./ContentPanel.vue";
import DownloadsPanel from "./DownloadsPanel.vue";
import ImportPanel from "./ImportPanel.vue";
import SyncPanel from "./SyncPanel.vue";
import PromptDialog from "../../components/PromptDialog.vue";
import ConfirmDialog from "../../components/ConfirmDialog.vue";
vi.mock("../../api/client", async (original) => ({
  ...(await original<typeof import("../../api/client")>()),
  api: (await import("../../test/client")).testClient(),
}));
const api = useAppApi();
const messages = () =>
  useToasts()
    .value.map((t) => t.message)
    .join("\n");

it("filters and pages taxonomy, renames and toggles tags without changing ids", async () => {
  for (let i = 0; i < 22; i++) api.db.taxonomy.push(makeTax(`tag-${i}`));
  const { wrapper } = await renderView(ContentPanel);
  expect(wrapper.findAll("tbody tr")).toHaveLength(20);
  await click(wrapper, "Next");
  expect(wrapper.text()).toContain("page 2 of 2");
  await click(wrapper, "Prev");
  await input(wrapper, '[aria-label="Search taxonomy"]', "Action");
  expect(wrapper.findAll("tbody tr")).toHaveLength(1);
  await input(wrapper, 'select[aria-label="Filter by type"]', "Genre");
  await click(wrapper, "Action");
  const field = wrapper.get("tbody input[type=text]");
  await field.setValue("Adventure");
  await field.trigger("keyup.enter");
  await flushPromises();
  expect(api.db.taxonomy[0]!.name).toBe("Adventure");
  expect(api.writes().at(-1)?.body).toEqual({ name: "Adventure" });
  await input(wrapper, '[aria-label="Search taxonomy"]', "Adventure");
  await click(wrapper, "Adventure");
  await wrapper.get("tbody input[type=text]").trigger("keyup.escape");
  await click(wrapper, "Adventure");
  await wrapper.get("tbody input[type=text]").trigger("blur");
  await flushPromises();
  expect(api.writes().filter((r) => r.body.name === "Adventure")).toHaveLength(1);
  await input(wrapper, "tbody input[type=checkbox]", false);
  expect(api.db.taxonomy[0]!.enabled).toBe(false);
  await input(wrapper, '[aria-label="Search taxonomy"]', "absent");
  expect(wrapper.text()).toContain("No entries match");
});

it("keeps taxonomy drafts on rejected writes and supports tag/alias creation and deletion", async () => {
  api.db.taxonomy[0]!.aliases = [{ id: "old", name: "Old alias", tagId: "action" }];
  const { wrapper } = await renderView(ContentPanel);
  await click(wrapper, "Add");
  let dialog = wrapper.findAllComponents(PromptDialog)[0]!;
  await input(dialog, "input", "  New genre  ");
  api.failNext("POST", "/api/taxonomy");
  await click(dialog, "Add tag");
  expect(dialog.get("input").element.value).toContain("New genre");
  expect(messages()).toContain("Rejected by server");
  await click(dialog, "Add tag");
  expect(api.db.taxonomy.at(-1)?.name).toBe("New genre");
  expect(dialog.props("open")).toBe(false);
  const row = wrapper.findAll("tbody tr").find((r) => r.text().includes("Action"))!;
  await row.get('[aria-label="Add alias"]').trigger("click");
  await flushPromises();
  dialog = wrapper.findAllComponents(PromptDialog)[1]!;
  await input(dialog, "input", "Synonym");
  api.failNext("POST", "/api/taxonomy/action/aliases");
  await click(dialog, "Add alias");
  expect(dialog.props("open")).toBe(true);
  await click(dialog, "Add alias");
  expect(api.db.taxonomy[0]!.aliases).toContainEqual({
    id: "new-alias",
    name: "Synonym",
    tagId: "action",
  });
  api.failNext("DELETE", "/api/taxonomy/action/aliases/old");
  await row.get('[aria-label="Remove alias"]').trigger("click");
  await flushPromises();
  expect(row.text()).toContain("Old alias");
  await row.get('[aria-label="Remove alias"]').trigger("click");
  await flushPromises();
  expect(row.text()).not.toContain("Old alias");
  api.failNext("PATCH", "/api/taxonomy/action");
  await click(wrapper, "Action");
  await input(wrapper, "tbody input[type=text]", "Failed name");
  await wrapper.get("tbody input[type=text]").trigger("keyup.enter");
  await flushPromises();
  expect(row.text()).toContain("Action");
  api.failNext("DELETE", "/api/taxonomy/action");
  await row
    .findAll("button")
    .find((b) => b.text() === "Delete")!
    .trigger("click");
  await flushPromises();
  expect(row.text()).toContain("Action");
  await row
    .findAll("button")
    .find((b) => b.text() === "Delete")!
    .trigger("click");
  await flushPromises();
  expect(api.db.taxonomy.some((t) => t.id === "action")).toBe(false);
  await click(wrapper, "Add");
  await wrapper.findAllComponents(PromptDialog)[0]!.get('[aria-label="Close"]').trigger("click");
});

it("refreshes taxonomy after completion and preserves controls on refresh failure", async () => {
  const { wrapper } = await renderView(ContentPanel);
  api.failNext("POST", "/api/taxonomy/refresh");
  await click(wrapper, "Refresh");
  expect(messages()).toContain("Rejected by server");
  await click(wrapper, "Refresh");
  taskEvent("taxonomy", "running");
  await flushPromises();
  expect(button(wrapper, "Refreshing…").attributes("disabled")).toBeDefined();
  api.db.taxonomy.push(makeTax("from-provider"));
  taskEvent("taxonomy", "done", { result: { added: 1 } });
  await flushPromises();
  expect(wrapper.text()).toContain("from-provider");
  taskEvent("taxonomy");
  taskEvent("scan");
  await flushPromises();
  expect(messages()).toContain("Added 0 new");
});

it("renders download phases and sizes and performs individual queue actions", async () => {
  api.db.downloads = [
    makeDownload("q"),
    makeDownload("p", "paused"),
    makeDownload("f", "failed"),
    makeDownload("done", "done", { sizeBytes: 2e6 }),
    makeDownload("fetch", "downloading", {
      phase: "fetching",
      detail: "1/3",
      progress: 25,
      sizeBytes: 100,
    }),
    makeDownload("encode", "downloading", { phase: "encoding", progress: 80, sizeBytes: 2300 }),
    makeDownload("unknown", "downloading", { progress: 1 }),
  ];
  api.db.sync.lastSync = new Date().toISOString();
  const { wrapper } = await renderView(DownloadsPanel);
  expect(wrapper.text()).toContain("Fetching · 1/3 · 25%");
  expect(wrapper.text()).toContain("Encoding · 80%");
  expect(wrapper.text()).toContain("2.0 MB");
  expect(wrapper.text()).toContain("1 KB");
  await wrapper.get('[aria-label="Pause"]').trigger("click");
  await flushPromises();
  expect(api.db.downloads[0]!.status).toBe("paused");
  await wrapper.get('[aria-label="Resume"]').trigger("click");
  await flushPromises();
  expect(api.db.downloads[0]!.status).toBe("queued");
  await wrapper.get('[aria-label="Retry"]').trigger("click");
  await flushPromises();
  expect(messages()).toContain("Download queued");
  await wrapper.get('[aria-label="Remove"]').trigger("click");
  await flushPromises();
  expect(api.db.downloads.some((d) => d.id === "q")).toBe(false);
  await click(wrapper, "Clear completed");
  expect(api.db.downloads.some((d) => d.status === "done")).toBe(false);
  await input(wrapper, '[aria-label="Parallel downloads"]', "5");
  expect(api.db.downloadConfig.parallelDownloads).toBe(5);
  expect(messages()).toContain("Parallel downloads set to 5");
  api.failNext("PATCH", "/api/downloads/config");
  await input(wrapper, '[aria-label="Parallel downloads"]', "99");
  expect(messages()).toContain("Rejected by server");
  await click(wrapper, "Sync now");
  expect(button(wrapper, "Syncing…").attributes("disabled")).toBeDefined();
  taskEvent("sync", "done", { result: { newChapters: 3 } });
  await flushPromises();
  expect(messages()).toContain("Sync complete — 3 new");
  taskEvent("sync", "failed");
  taskEvent("download");
  taskEvent("unrelated");
  await flushPromises();
});

it("requires confirmation to cancel, handles bulk rejection, and throttles progress reloads", async () => {
  api.db.downloads = [makeDownload("q"), makeDownload("p", "paused")];
  const { wrapper } = await renderView(DownloadsPanel);
  api.failNext("POST", "/api/downloads");
  await click(wrapper, "Pause all");
  expect(messages()).toContain("Rejected by server");
  await click(wrapper, "Pause all");
  expect(api.db.downloads.every((d) => d.status === "paused")).toBe(true);
  await click(wrapper, "Resume all");
  expect(api.db.downloads.every((d) => d.status === "queued")).toBe(true);
  await click(wrapper, "Cancel all");
  const dialog = wrapper.getComponent(ConfirmDialog);
  await dialog.get('[aria-label="Close"]').trigger("click");
  expect(api.db.downloads).toHaveLength(2);
  await click(wrapper, "Cancel all");
  await click(dialog, "Cancel all");
  expect(api.db.downloads).toEqual([]);
  expect(wrapper.text()).toContain("No downloads");
  vi.useFakeTimers();
  try {
    const before = api.requests.filter(
      (r) => r.path === "/api/downloads" && r.method === "GET",
    ).length;
    taskEvent("download", "running");
    taskEvent("download", "running");
    taskEvent("other", "running");
    await vi.advanceTimersByTimeAsync(399);
    expect(
      api.requests.filter((r) => r.path === "/api/downloads" && r.method === "GET"),
    ).toHaveLength(before);
    await vi.advanceTimersByTimeAsync(1);
    await flushPromises();
    expect(
      api.requests.filter((r) => r.path === "/api/downloads" && r.method === "GET"),
    ).toHaveLength(before + 1);
    taskEvent("download", "running");
    wrapper.unmount();
    await vi.advanceTimersByTimeAsync(400);
    expect(
      api.requests.filter((r) => r.path === "/api/downloads" && r.method === "GET"),
    ).toHaveLength(before + 1);
  } finally {
    vi.useRealTimers();
  }
});

it("persists import preferences and saves, overwrites, applies, and deletes filename presets", async () => {
  api.db.importConfig.quality = 90;
  const { wrapper } = await renderView(ImportPanel);
  expect(api.writes()).toEqual([]);
  expect(wrapper.get<HTMLSelectElement>('[aria-label="Import image quality"]').element.value).toBe(
    "75",
  );
  await input(wrapper, "input[type=checkbox]", false);
  expect(wrapper.text()).toContain("Enable local import to use this");
  await input(wrapper, "input[type=checkbox]", true);
  await wrapper.get('[aria-label="Import image quality"]').setValue("60");
  await input(wrapper, '[placeholder="{series} - c{chapter} (v{volume})"]', "{series}_{chapter}");
  await input(wrapper, '[placeholder="Name this pattern"]', " Custom ");
  await click(wrapper, "Save preset");
  expect(api.db.importConfig.patternPresets.at(-1)?.name).toBe("Custom");
  await input(wrapper, '[placeholder="Name this pattern"]', "Custom");
  await click(wrapper, "Save preset");
  expect(api.db.importConfig.patternPresets.filter((p) => p.name === "Custom")).toHaveLength(1);
  await wrapper
    .findAll("button")
    .find((b) => b.text().includes("Default") && b.text().includes("{series}"))!
    .trigger("click");
  await flushPromises();
  expect(api.db.importConfig.filenamePattern).toBe("{series} - {chapter}");
  await wrapper.get('[aria-label="Delete preset"]').trigger("click");
  await flushPromises();
  expect(api.db.importConfig.patternPresets.some((p) => p.name === "Default")).toBe(false);
  await input(wrapper, '[placeholder="Name this pattern"]', " ");
  await wrapper.get<HTMLInputElement>('[placeholder="Name this pattern"]').trigger("keyup.enter");
});

it("retries rejected imports and resets the path after successful task completion", async () => {
  const { wrapper } = await renderView(ImportPanel);
  await input(
    wrapper,
    '[placeholder="/data/incoming/Series  or  /data/file.cbz"]',
    " /media/book.cbz ",
  );
  await wrapper.get('[aria-label="Import kind"]').setValue("comic");
  api.failNext("POST", "/api/import");
  await click(wrapper, "Import");
  expect(messages()).toContain("Rejected by server");
  await click(wrapper, "Import");
  expect(api.writes().at(-1)?.body).toEqual({ path: "/media/book.cbz", kind: "comic" });
  taskEvent("localimport", "running");
  await flushPromises();
  expect(button(wrapper, "Importing…").attributes("disabled")).toBeDefined();
  taskEvent("localimport", "failed");
  taskEvent("other");
  await flushPromises();
  expect(messages()).toContain("Import failed");
  taskEvent("localimport", "done", { result: { booksImported: 2 } });
  await flushPromises();
  expect(messages()).toContain("Imported 2 book(s)");
  expect(
    wrapper.get<HTMLInputElement>('[placeholder="/data/incoming/Series  or  /data/file.cbz"]')
      .element.value,
  ).toBe("");
});

it("uploads one or multiple files and permits retrying the same rejected file", async () => {
  const { wrapper } = await renderView(ImportPanel);
  const upload = wrapper.get<HTMLInputElement>("input[type=file]");
  async function send(names: string[]) {
    Object.defineProperty(upload.element, "files", {
      configurable: true,
      value: names.map((name) => new File(["data"], name)),
    });
    await upload.trigger("change");
    await flushPromises();
  }
  await send([]);
  expect(api.writes()).toHaveLength(0);
  api.failNext("POST", "/api/import/upload");
  await send(["book.cbz"]);
  expect(messages()).toContain("Upload failed");
  await send(["book.cbz"]);
  expect(messages()).toContain("Upload started");
  await send(["one.cbz", "two.zip"]);
  expect(messages()).toContain("Uploading 2 files");
  expect(api.writes().at(-1)?.body).toEqual({ kind: "manga", files: ["one.cbz", "two.zip"] });
});

it("manages background sync jobs, displays file/manga progress and errors, and enforces parallel sync limits", async () => {
  api.db.sync.lastSync = new Date().toISOString();
  api.db.sync.jobs = [
    {
      id: "j-run",
      kind: "sync",
      title: "Berserk",
      source: "MangaDex",
      status: "running",
      progress: 45,
      detail: "Pulling chapters for Berserk from MangaDex",
      error: null,
    },
    {
      id: "j-err",
      kind: "scan",
      title: "Corrupt.cbz",
      source: "/library/Manga",
      status: "failed",
      progress: 0,
      detail: "Unreadable file while indexing Corrupt.cbz",
      error: "Bad zip header",
    },
  ];
  const { wrapper } = await renderView(SyncPanel);
  expect(wrapper.text()).toContain("Berserk");
  expect(wrapper.text()).toContain("from MangaDex");
  expect(wrapper.text()).toContain("Pulling chapters for Berserk from MangaDex");
  expect(wrapper.text()).toContain("Corrupt.cbz");
  expect(wrapper.text()).toContain("Bad zip header");

  await input(wrapper, '[aria-label="Parallel sync jobs"]', "6");
  expect(api.db.sync.parallelSyncs).toBe(6);
  expect(messages()).toContain("Parallel sync jobs set to 6");
  api.failNext("PATCH", "/api/sync/config");
  await input(wrapper, '[aria-label="Parallel sync jobs"]', "15");
  expect(messages()).toContain("Rejected by server");

  await wrapper.get('[aria-label="Pause job"]').trigger("click");
  await flushPromises();
  expect(api.db.sync.jobs[0]!.status).toBe("paused");
  expect(messages()).toContain("Sync paused");

  await wrapper.get('[aria-label="Resume job"]').trigger("click");
  await flushPromises();
  expect(api.db.sync.jobs[0]!.status).toBe("queued");
  expect(messages()).toContain("Sync resumed");

  await click(wrapper, "Pause all");
  expect(api.db.sync.paused).toBe(true);
  await click(wrapper, "Resume all");
  expect(api.db.sync.paused).toBe(false);

  api.failNext("POST", "/api/sync/control");
  await wrapper.get('[aria-label="Cancel job"]').trigger("click");
  await flushPromises();
  expect(messages()).toContain("Rejected by server");

  await click(wrapper, "Cancel all");
  expect(api.db.sync.jobs[0]!.status).toBe("cancelled");

  await click(wrapper, "Clear completed");
  expect(api.db.sync.jobs).toEqual([]);
  expect(wrapper.text()).toContain("No sync jobs.");

  await click(wrapper, "Sync now");
  expect(messages()).toContain("Checking for new chapters");
  taskEvent("sync", "done");
  await flushPromises();
  wrapper.unmount();

  vi.useFakeTimers();
  try {
    api.db.sync.lastSync = null;
    const mounted = await renderView(SyncPanel);
    const before = api.requests.filter((r) => r.path === "/api/sync" && r.method === "GET").length;
    taskEvent("scan", "running");
    taskEvent("scan", "running");
    taskEvent("unrelated", "running");
    await vi.advanceTimersByTimeAsync(300);
    await flushPromises();
    expect(api.requests.filter((r) => r.path === "/api/sync" && r.method === "GET")).toHaveLength(
      before + 1,
    );
    taskEvent("import", "running");
    mounted.wrapper.unmount();
    await vi.advanceTimersByTimeAsync(300);
  } finally {
    vi.useRealTimers();
  }
});

it.each([DownloadsPanel, SyncPanel])(
  "recovers the sync button when starting sync fails",
  async (panel) => {
    const { wrapper } = await renderView(panel);
    api.failNext("POST", "/api/sync", "Sync unavailable", 503);
    await click(wrapper, "Sync now");
    expect(messages()).toContain("Sync unavailable");
    expect(button(wrapper, "Sync now").attributes("disabled")).toBeUndefined();
  },
);

it("shows an already running sync when opening Downloads and labels chapter overall progress", async () => {
  api.db.sync.syncing = true;
  api.db.downloads = [makeDownload("active", "downloading")];
  const { wrapper } = await renderView(DownloadsPanel);
  expect(button(wrapper, "Syncing…").attributes("disabled")).toBeDefined();
  expect(wrapper.text()).toContain("Overall progress");
});
