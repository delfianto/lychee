import { mount, flushPromises } from "@vue/test-utils";
import { beforeEach, expect, it, vi } from "vite-plus/test";
import Lightbox from "./Lightbox.vue";
import { TestPlayer } from "../test/player";
import { useReaderSettings } from "../lib/readerSettings";
vi.mock("plyr", async () => ({ default: (await import("../test/player")).TestPlayer }));
const items = [
  { index: 0, kind: "image" as const, url: "/still", thumbUrl: "/thumb" },
  { index: 1, kind: "video" as const, url: "/video", thumbUrl: "/thumb", posterUrl: "/poster" },
];
beforeEach(() => {
  TestPlayer.instances = [];
  Object.assign(useReaderSettings(), { videoAutoPlay: true, videoAutoNext: true });
});
async function key(key: string) {
  window.dispatchEvent(new KeyboardEvent("keydown", { key }));
  await flushPromises();
}
it("wraps keyboard and button navigation and closes from each dismiss control", async () => {
  const wrapper = mount(Lightbox, { props: { items, index: 0 }, attachTo: document.body });
  await flushPromises();
  await key("ArrowLeft");
  await key("ArrowRight");
  expect(wrapper.emitted("update:index")).toEqual([[1], [1]]);
  await wrapper.get('[aria-label="Previous"]').trigger("click");
  await wrapper.get('[aria-label="Next"]').trigger("click");
  await wrapper.get('[aria-label="Close"]').trigger("click");
  await key("Escape");
  await wrapper.get(".fixed").trigger("click");
  expect(wrapper.emitted("close")).toHaveLength(3);
  const updates = wrapper.emitted("update:index")?.length;
  wrapper.unmount();
  await key("ArrowRight");
  expect(wrapper.emitted("update:index")?.length ?? updates).toBe(updates);
});
it("mounts and destroys video playback and honors autoplay/auto-next preferences", async () => {
  const wrapper = mount(Lightbox, { props: { items, index: 1 }, attachTo: document.body });
  await flushPromises();
  const player = TestPlayer.instances[0]!;
  expect(player.options.autoplay).toBe(true);
  expect(wrapper.get("video").attributes("poster")).toBe("/poster");
  player.play.mockRejectedValueOnce(new Error("autoplay blocked"));
  player.emit("ready");
  await flushPromises();
  expect(player.play).toHaveBeenCalledOnce();
  player.emit("ended");
  expect(wrapper.emitted("update:index")).toEqual([[0]]);
  useReaderSettings().videoAutoNext = false;
  player.emit("ended");
  expect(wrapper.emitted("update:index")).toHaveLength(1);
  const focused = document.createElement("div");
  focused.className = "plyr";
  document.body.append(focused);
  focused.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
  expect(wrapper.emitted("update:index")).toHaveLength(1);
  await wrapper.setProps({ index: 0 });
  expect(player.off).toHaveBeenCalledWith("ended", expect.any(Function));
  expect(player.destroy).toHaveBeenCalledOnce();
  useReaderSettings().videoAutoPlay = false;
  await wrapper.setProps({ index: 1 });
  await flushPromises();
  expect(TestPlayer.instances.at(-1)!.options.autoplay).toBe(false);
  TestPlayer.instances.at(-1)!.destroy.mockImplementationOnce(() => {
    throw new Error("already destroyed");
  });
  wrapper.unmount();
});
it("handles an empty collection without emitting an invalid index", async () => {
  const wrapper = mount(Lightbox, { props: { items: [], index: 0 } });
  await key("ArrowRight");
  await key("other");
  expect(wrapper.emitted("update:index")).toBeUndefined();
});

it("keeps the next video's player connected after Plyr restores a clone", async () => {
  const videos = [items[1]!, { ...items[1]!, index: 2, url: "/second-video" }];
  const wrapper = mount(Lightbox, { props: { items: videos, index: 0 }, attachTo: document.body });
  await flushPromises();
  const first = TestPlayer.instances.at(-1)!;
  await wrapper.setProps({ index: 1 });
  await flushPromises();
  const second = TestPlayer.instances.at(-1)!;
  expect(first.destroy).toHaveBeenCalledOnce();
  expect(second).not.toBe(first);
  expect(second.element.isConnected).toBe(true);
  expect(second.element.getAttribute("src")).toBe("/second-video");
  expect(wrapper.get("video").element).toBe(second.element);
  expect(wrapper.findAll(".plyr")).toHaveLength(1);
  first.emit("ready");
  expect(first.play).not.toHaveBeenCalled();
  second.emit("ready");
  expect(second.play).toHaveBeenCalledOnce();
  await wrapper.setProps({ items: videos.map((video) => ({ ...video })) });
  await flushPromises();
  expect(second.destroy).not.toHaveBeenCalled();
  expect(wrapper.get("video").element).toBe(second.element);
  await wrapper.setProps({ index: 0 });
  await flushPromises();
  expect(TestPlayer.instances.at(-1)!.element.isConnected).toBe(true);
  expect(wrapper.get("video").attributes("src")).toBe("/video");
});

it("cancels a pending player mount when the lightbox closes", async () => {
  const wrapper = mount(Lightbox, { props: { items, index: 1 }, attachTo: document.body });
  wrapper.unmount();
  await flushPromises();
  expect(TestPlayer.instances).toHaveLength(0);
});
