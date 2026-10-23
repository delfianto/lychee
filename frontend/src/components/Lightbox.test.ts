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
