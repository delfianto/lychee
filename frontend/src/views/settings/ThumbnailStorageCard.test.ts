import { flushPromises } from "@vue/test-utils";
import { describe, expect, it, vi } from "vite-plus/test";
import { useMainBarIcons, useRecentlyAddedKinds } from "../../lib/density";
import { useAppApi } from "../../test/appApi";
import { renderView, input, button, click } from "../../test/views";
import ThumbnailStorageCard from "./ThumbnailStorageCard.vue";

vi.mock("../../api/client", async (original) => ({
  ...(await original<typeof import("../../api/client")>()),
  api: (await import("../../test/client")).testClient(),
}));
const api = useAppApi();
const url = "/api/libraries/thumbnail-storage";

async function submit(wrapper: Awaited<ReturnType<typeof renderView>>["wrapper"]) {
  await wrapper.get("form").trigger("submit");
  await flushPromises();
}

describe("thumbnail storage", () => {
  it("loads defaults, saves a custom path, restores it on remount, and resets to default", async () => {
    const { wrapper } = await renderView(ThumbnailStorageCard);
    const defaultField = wrapper.get<HTMLInputElement>('input[type="text"]');
    expect(defaultField.element.value).toBe("/storage/thumbnails");
    expect(defaultField.attributes("disabled")).toBeUndefined();
    expect(button(wrapper, "Browse").attributes("disabled")).toBeUndefined();
    expect(api.writes()).toEqual([]);
    expect(wrapper.findAll("button").some((b) => b.text() === "Save thumbnail storage")).toBe(
      false,
    );
    expect(wrapper.find("select").exists()).toBe(false);
    await input(wrapper, 'input[type="text"]', " /data/thumbs ");
    await submit(wrapper);
    expect(api.writes().at(-1)).toMatchObject({
      method: "PUT",
      path: url,
      body: { path: "/data/thumbs" },
    });
    wrapper.unmount();
    const second = (await renderView(ThumbnailStorageCard)).wrapper;
    expect((second.get('input[type="text"]').element as HTMLInputElement).value).toBe(
      "/data/thumbs",
    );
    await click(second, "Use default folder");
    expect((second.get('input[type="text"]').element as HTMLInputElement).value).toBe(
      "/storage/thumbnails",
    );
    expect(second.get('input[type="text"]').attributes("disabled")).toBeUndefined();
    await submit(second);
    expect(api.writes().at(-1)?.body).toEqual({ path: null });
  });

  it("rejects empty paths and resets unsaved edits without writing settings", async () => {
    const { wrapper } = await renderView(ThumbnailStorageCard);
    await submit(wrapper);
    expect(api.writes()).toEqual([]);
    await input(wrapper, 'input[type="text"]', "  ");
    expect(button(wrapper, "Save thumbnail storage").attributes("disabled")).toBeDefined();
    await submit(wrapper);
    expect(api.writes()).toEqual([]);
    await click(wrapper, "Use default folder");
    expect((wrapper.get('input[type="text"]').element as HTMLInputElement).value).toBe(
      "/storage/thumbnails",
    );
    expect(wrapper.text()).toContain("Using the default folder");
    expect(api.writes()).toEqual([]);
    expect(wrapper.findAll("button").some((b) => b.text() === "Save thumbnail storage")).toBe(
      false,
    );
  });

  it("defaults recently added content to manga and updates multi-select kinds and main bar icon toggles", async () => {
    useRecentlyAddedKinds().recentlyAddedKinds.value = ["manga"];
    useMainBarIcons().mainBarIcons.value = { comics: true, gallery: true, lists: true };
    const { wrapper } = await renderView(ThumbnailStorageCard);
    const trigger = wrapper.get('[aria-label="Recently added content"]');
    expect(trigger.text()).toBe("Manga");
    await wrapper.get('input[aria-label="Comics"]').trigger("change");
    expect(trigger.text()).toBe("Manga, Comics");
    await wrapper.get('input[aria-label="Gallery"]').trigger("change");
    expect(trigger.text()).toBe("Manga, Comics, Gallery");
    await wrapper.get('input[aria-label="Manga"]').trigger("change");
    await wrapper.get('input[aria-label="Comics"]').trigger("change");
    await wrapper.get('input[aria-label="Gallery"]').trigger("change");
    expect(trigger.text()).toBe("None");
    await wrapper.get('input[aria-label="Manga"]').trigger("change");
    expect(useRecentlyAddedKinds().recentlyAddedKinds.value).toEqual(["manga"]);

    const comicsToggle = wrapper.get<HTMLInputElement>('input[aria-label="Show Comics icon"]');
    const galleryToggle = wrapper.get<HTMLInputElement>('input[aria-label="Show Gallery icon"]');
    expect(comicsToggle.element.checked).toBe(true);
    expect(galleryToggle.element.checked).toBe(true);
    const listsToggle = wrapper.get<HTMLInputElement>('input[aria-label="Show Lists icon"]');
    expect(listsToggle.element.checked).toBe(true);
    await comicsToggle.setValue(false);
    expect(useMainBarIcons().mainBarIcons.value).toEqual({
      comics: false,
      gallery: true,
      lists: true,
    });
    await galleryToggle.setValue(false);
    expect(useMainBarIcons().mainBarIcons.value).toEqual({
      comics: false,
      gallery: false,
      lists: true,
    });
    await listsToggle.setValue(false);
    expect(useMainBarIcons().mainBarIcons.value.lists).toBe(false);
    await listsToggle.setValue(true);
    expect(useMainBarIcons().mainBarIcons.value.lists).toBe(true);
  });

  it("retries failed loads and keeps edits on a failed save", async () => {
    api.failNext("GET", url, "Storage unavailable");
    const { wrapper } = await renderView(ThumbnailStorageCard);
    expect(wrapper.get('[role="alert"]').text()).toBe("Storage unavailable");
    expect(wrapper.find("select").exists()).toBe(false);
    await click(wrapper, "Retry");
    await input(wrapper, 'input[type="text"]', "/readonly");
    api.failNext("PUT", url, "Folder is not writable");
    await submit(wrapper);
    expect(wrapper.get('[role="alert"]').text()).toBe("Folder is not writable");
    expect((wrapper.get('input[type="text"]').element as HTMLInputElement).value).toBe("/readonly");
    expect(button(wrapper, "Save thumbnail storage").attributes("disabled")).toBeUndefined();
  });
});
