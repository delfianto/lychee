import { flushPromises } from "@vue/test-utils";
import { describe, expect, it, vi } from "vite-plus/test";
import { useAppApi } from "../../test/appApi";
import { renderView, input, button, click } from "../../test/views";
import ImageProcessingSettings from "./ImageProcessingSettings.vue";

vi.mock("../../api/client", async (original) => ({
  ...(await original<typeof import("../../api/client")>()),
  api: (await import("../../test/client")).testClient(),
}));
const api = useAppApi();
const url = "/api/libraries/image-processing";
const conversion = 'input[aria-label="Conversion workers"]';
const thumbnails = 'input[aria-label="Thumbnail workers"]';

describe("independent image workers", () => {
  it("loads, recommends CPU budgets, saves independently, and restores on remount", async () => {
    const { wrapper } = await renderView(ImageProcessingSettings);
    expect(wrapper.text()).toContain("32 CPU threads available");
    expect(button(wrapper, "Save image processing").attributes("disabled")).toBeDefined();
    await click(wrapper, "Use recommended (16 / 4)");
    expect(wrapper.get<HTMLInputElement>(conversion).element.value).toBe("16");
    expect(wrapper.get<HTMLInputElement>(thumbnails).element.value).toBe("4");
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(api.writes()).toEqual([
      expect.objectContaining({
        method: "PUT",
        path: url,
        body: { conversionWorkers: 16, thumbnailWorkers: 4 },
      }),
    ]);
    expect(button(wrapper, "Save image processing").attributes("disabled")).toBeDefined();
    wrapper.unmount();
    const second = (await renderView(ImageProcessingSettings)).wrapper;
    expect(second.get<HTMLInputElement>(conversion).element.value).toBe("16");
    await input(second, thumbnails, "8");
    await second.get("form").trigger("submit");
    await flushPromises();
    expect(api.writes().at(-1)?.body).toEqual({ conversionWorkers: 16, thumbnailWorkers: 8 });
  });

  it.each(["0", "-1", "65", "1.5", ""])("blocks invalid worker count %s", async (value) => {
    const { wrapper } = await renderView(ImageProcessingSettings);
    await input(wrapper, conversion, value);
    expect(button(wrapper, "Save image processing").attributes("disabled")).toBeDefined();
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(api.writes()).toEqual([]);
  });

  it("retries load failures and keeps edits after a failed save", async () => {
    api.failNext("GET", url, "Worker settings unavailable");
    const { wrapper } = await renderView(ImageProcessingSettings);
    expect(wrapper.get('[role="alert"]').text()).toBe("Worker settings unavailable");
    await click(wrapper, "Retry worker settings");
    await input(wrapper, conversion, "10");
    api.failNext("PUT", url, "Could not save workers");
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toBe("Could not save workers");
    expect(wrapper.get<HTMLInputElement>(conversion).element.value).toBe("10");
    expect(button(wrapper, "Save image processing").attributes("disabled")).toBeUndefined();
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(wrapper.find('[role="alert"]').exists()).toBe(false);
    expect(api.writes().at(-1)?.body).toEqual({ conversionWorkers: 10, thumbnailWorkers: 1 });
  });
});
