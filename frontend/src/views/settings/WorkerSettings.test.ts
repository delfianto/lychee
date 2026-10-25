import { flushPromises } from "@vue/test-utils";
import { http, HttpResponse } from "msw";
import { expect, it, vi } from "vite-plus/test";
import { useAppApi } from "../../test/appApi";
import { renderView, input, button, click } from "../../test/views";
import LibrariesPanel from "./LibrariesPanel.vue";
import WorkerSettings from "./WorkerSettings.vue";

vi.mock("../../api/client", async (original) => ({
  ...(await original<typeof import("../../api/client")>()),
  api: (await import("../../test/client")).testClient(),
}));
const api = useAppApi();
const url = "/api/libraries/workers";
const download = 'input[aria-label="Download workers"]';
const scan = 'input[aria-label="Scan/metadata I/O workers"]';
const conversion = 'input[aria-label="Conversion workers"]';
const thumbnails = 'input[aria-label="Thumbnail workers"]';
const form = 'form[aria-label="Worker settings"]';

it("keeps the two worker rows with one save that persists all four limits", async () => {
  api.db.downloadConfig.parallelDownloads = 10;
  api.db.sync.parallelSyncs = 3;
  const { wrapper } = await renderView(LibrariesPanel);
  expect(wrapper.text().indexOf("I/O workers")).toBeLessThan(
    wrapper.text().indexOf("Image processing"),
  );
  expect(wrapper.get<HTMLInputElement>(download).element.value).toBe("10");
  expect(wrapper.get<HTMLInputElement>(scan).element.value).toBe("3");
  expect(wrapper.get(form).findAll('button[type="submit"]')).toHaveLength(1);
  expect(button(wrapper, "Save workers").attributes("disabled")).toBeDefined();
  expect(api.writes()).toEqual([]);
  await input(wrapper, download, "5");
  await input(wrapper, scan, "7");
  await input(wrapper, conversion, "12");
  await input(wrapper, thumbnails, "4");
  await wrapper.get(form).trigger("submit");
  await flushPromises();
  expect(api.writes()).toEqual([
    expect.objectContaining({
      method: "PUT",
      path: url,
      body: {
        downloadWorkers: 5,
        scanMetadataWorkers: 7,
        conversionWorkers: 12,
        thumbnailWorkers: 4,
      },
    }),
  ]);
  expect(button(wrapper, "Save workers").attributes("disabled")).toBeDefined();
  wrapper.unmount();
  const second = (await renderView(WorkerSettings)).wrapper;
  for (const [selector, value] of [
    [download, "5"],
    [scan, "7"],
    [conversion, "12"],
    [thumbnails, "4"],
  ])
    expect(second.get<HTMLInputElement>(selector!).element.value).toBe(value);
});

it("auto detects fresh CPU recommendations while preserving I/O edits, without saving", async () => {
  const { wrapper } = await renderView(WorkerSettings);
  await input(wrapper, download, "5");
  await input(wrapper, scan, "7");
  Object.assign(api.db.imageProcessing, {
    cpuThreads: 16,
    recommendedConversionWorkers: 8,
    recommendedThumbnailWorkers: 2,
  });
  await click(wrapper, "Auto detect");
  expect(wrapper.text()).toContain("16 CPU threads available");
  expect(wrapper.get<HTMLInputElement>(conversion).element.value).toBe("8");
  expect(wrapper.get<HTMLInputElement>(thumbnails).element.value).toBe("2");
  expect(wrapper.get<HTMLInputElement>(download).element.value).toBe("5");
  expect(wrapper.get<HTMLInputElement>(scan).element.value).toBe("7");
  expect(api.writes()).toEqual([]);
  expect(
    wrapper
      .get(form)
      .findAll("button")
      .map((b) => b.text()),
  ).toEqual(["Auto detect", "Save workers"]);
  await wrapper.get(form).trigger("submit");
  await flushPromises();
  expect(api.writes().at(-1)?.body).toEqual({
    downloadWorkers: 5,
    scanMetadataWorkers: 7,
    conversionWorkers: 8,
    thumbnailWorkers: 2,
  });
});

it.each(
  [download, scan, conversion, thumbnails].flatMap((selector) =>
    ["0", "1.5", "", selector === download || selector === scan ? "11" : "65"].map((value) => ({
      selector,
      value,
    })),
  ),
)("blocks invalid worker value $value in $selector", async ({ selector, value }) => {
  const { wrapper } = await renderView(WorkerSettings);
  await input(wrapper, selector, value);
  expect(button(wrapper, "Save workers").attributes("disabled")).toBeDefined();
  await wrapper.get(form).trigger("submit");
  await flushPromises();
  expect(api.writes()).toEqual([]);
});

it("retries load errors and preserves all edits after save failure", async () => {
  api.failNext("GET", url, "Workers unavailable");
  const { wrapper } = await renderView(WorkerSettings);
  expect(wrapper.get('[role="alert"]').text()).toBe("Workers unavailable");
  expect(wrapper.find(download).exists()).toBe(false);
  expect(api.writes()).toEqual([]);
  await click(wrapper, "Retry worker settings");
  await input(wrapper, download, "10");
  await input(wrapper, scan, "6");
  await input(wrapper, conversion, "16");
  await input(wrapper, thumbnails, "8");
  api.failNext("PUT", url, "Cannot save workers");
  await wrapper.get(form).trigger("submit");
  await flushPromises();
  expect(wrapper.get('[role="alert"]').text()).toBe("Cannot save workers");
  expect(api.db.downloadConfig.parallelDownloads).toBe(1);
  expect(api.db.sync.parallelSyncs).toBe(1);
  expect(api.db.imageProcessing.conversionWorkers).toBe(1);
  expect(api.db.imageProcessing.thumbnailWorkers).toBe(1);
  expect(button(wrapper, "Save workers").attributes("disabled")).toBeUndefined();
  await wrapper.get(form).trigger("submit");
  await flushPromises();
  expect(wrapper.find('[role="alert"]').exists()).toBe(false);
  expect(api.writes().at(-1)?.body).toEqual({
    downloadWorkers: 10,
    scanMetadataWorkers: 6,
    conversionWorkers: 16,
    thumbnailWorkers: 8,
  });
});

it("keeps manual edits when auto detection fails", async () => {
  const { wrapper } = await renderView(WorkerSettings);
  await input(wrapper, conversion, "10");
  api.failNext("GET", url, "Detection unavailable");
  await click(wrapper, "Auto detect");
  expect(wrapper.get('[role="alert"]').text()).toBe("Detection unavailable");
  expect(wrapper.get<HTMLInputElement>(conversion).element.value).toBe("10");
  expect(button(wrapper, "Save workers").attributes("disabled")).toBeUndefined();
  expect(api.writes()).toEqual([]);
});

it("blocks duplicate submissions and edits while a shared save is pending", async () => {
  const { wrapper } = await renderView(WorkerSettings);
  await input(wrapper, download, "5");
  let complete!: () => void;
  let requests = 0;
  api.server.use(
    http.put(`http://localhost${url}`, async () => {
      requests++;
      await new Promise<void>((resolve) => {
        complete = resolve;
      });
      return HttpResponse.json({
        ...api.db.imageProcessing,
        downloadWorkers: 5,
        scanMetadataWorkers: 1,
      });
    }),
  );
  await wrapper.get(form).trigger("submit");
  await flushPromises();
  expect(button(wrapper, "Saving…").attributes("disabled")).toBeDefined();
  expect(button(wrapper, "Auto detect").attributes("disabled")).toBeDefined();
  expect(wrapper.get(download).attributes("disabled")).toBeDefined();
  await wrapper.get(form).trigger("submit");
  await flushPromises();
  expect(requests).toBe(1);
  complete();
  await flushPromises();
  expect(wrapper.get(download).attributes("disabled")).toBeUndefined();
  expect(button(wrapper, "Save workers").attributes("disabled")).toBeDefined();
});
