import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vite-plus/test";
import type { FsListing } from "../api/client";
import { browsePath, makeDirectory } from "../api/settingsQueries";
import PathBrowserModal from "./PathBrowserModal.vue";
vi.mock("../api/settingsQueries", () => ({ browsePath: vi.fn(), makeDirectory: vi.fn() }));
function listing(path = "/media"): FsListing {
  return {
    root: "/media",
    path,
    parent: path === "/media" ? null : "/media",
    entries: [
      { name: "Manga", path: "/media/Manga", kind: "dir" },
      { name: "chapter.cbz", path: "/media/chapter.cbz", kind: "file" },
    ],
  };
}
function button(text: string): HTMLButtonElement {
  const result = Array.from(document.querySelectorAll("button")).find(
    (b) => b.textContent?.trim() === text,
  );
  if (!result) throw new Error(`Button not found: ${text}`);
  return result;
}
async function click(text: string) {
  button(text).click();
  await flushPromises();
}
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(browsePath).mockResolvedValue(listing());
});

it("falls back from an unavailable initial path to root and selects a directory", async () => {
  vi.mocked(browsePath).mockRejectedValueOnce(new Error("outside root"));
  const wrapper = mount(PathBrowserModal, {
    props: { initialPath: "/missing" },
    attachTo: document.body,
  });
  await flushPromises();
  expect(browsePath).toHaveBeenNthCalledWith(1, "/missing");
  expect(browsePath).toHaveBeenNthCalledWith(2, null);
  expect(button("chapter.cbz").disabled).toBe(true);
  vi.mocked(browsePath).mockResolvedValueOnce(listing("/media/Manga"));
  await click("Manga");
  expect(browsePath).toHaveBeenLastCalledWith("/media/Manga");
  await click("Use this folder");
  expect(wrapper.emitted("select")).toEqual([["/media/Manga"]]);
  await click("..");
  expect(browsePath).toHaveBeenLastCalledWith("/media");
  wrapper.unmount();
  expect(document.body.classList.contains("overflow-hidden")).toBe(false);
});

it("selects a file only when file selection is enabled", async () => {
  const wrapper = mount(PathBrowserModal, { props: { allowFiles: true }, attachTo: document.body });
  await flushPromises();
  await click("chapter.cbz");
  await click("Use this file");
  expect(wrapper.emitted("select")).toEqual([["/media/chapter.cbz"]]);
});

it("shows a read failure without offering a nonexistent path", async () => {
  vi.mocked(browsePath).mockRejectedValue(new Error("offline"));
  const wrapper = mount(PathBrowserModal, { attachTo: document.body });
  await flushPromises();
  expect(document.body.textContent).toContain("Couldn't read that folder");
  expect(button("Use this folder").disabled).toBe(true);
  await click("Cancel");
  expect(wrapper.emitted("close")).toHaveLength(1);
});

it("keeps a rejected new-folder draft available for correction and retry", async () => {
  vi.mocked(makeDirectory)
    .mockRejectedValueOnce(new Error("Already exists"))
    .mockResolvedValueOnce({ ...listing(), entries: [] });
  const wrapper = mount(PathBrowserModal, { attachTo: document.body });
  await flushPromises();
  await click("New folder");
  const input = document.querySelector<HTMLInputElement>('input[placeholder="Folder name"]')!;
  input.value = "  New  ";
  input.dispatchEvent(new Event("input", { bubbles: true }));
  await flushPromises();
  await click("Create");
  expect(makeDirectory).toHaveBeenCalledWith("/media", "New");
  expect(document.body.textContent).toContain("Already exists");
  expect(input.value).toBe("  New  ");
  await click("Create");
  expect(document.querySelector("input")).toBeNull();
  expect(document.body.textContent).toContain("Empty folder");
  await click("New folder");
  window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
  await flushPromises();
  expect(wrapper.emitted("close")).toBeUndefined();
  window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
  expect(wrapper.emitted("close")).toHaveLength(1);
});
