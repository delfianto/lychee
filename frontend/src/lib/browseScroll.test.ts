import { afterEach, beforeEach, expect, it, vi } from "vite-plus/test";
import { createBrowseScroll } from "./browseScroll";
let changed: () => void;
beforeEach(() => {
  vi.useFakeTimers();
  vi.spyOn(document.documentElement, "scrollHeight", "get").mockReturnValue(6000);
  vi.stubGlobal("innerHeight", 800);
  vi.stubGlobal(
    "MutationObserver",
    class {
      constructor(callback: () => void) {
        changed = callback;
      }
      observe() {}
      disconnect() {}
    },
  );
  document.body.innerHTML = '<main data-browse-route="/manga"></main>';
});
afterEach(() => {
  vi.clearAllTimers();
  vi.useRealTimers();
});
it("remembers a library offset for navigation and gives history offsets precedence", async () => {
  vi.spyOn(window, "scrollY", "get").mockReturnValue(3200);
  vi.spyOn(window, "scrollX", "get").mockReturnValue(12);
  const browsing = createBrowseScroll();
  browsing.remember("/manga");
  expect(await browsing.restore("/manga", null, true)).toEqual({ left: 12, top: 3200 });
  expect(await browsing.restore("/manga", { left: 0, top: 1800 }, true)).toEqual({
    left: 0,
    top: 1800,
  });
  expect(await browsing.restore("/manga", null, false)).toEqual({ left: 0, top: 0 });
});
it("waits for the actual returning route and all its retained pages", async () => {
  document.body.innerHTML = '<main data-browse-route="/series/work"></main>';
  const browsing = createBrowseScroll();
  const done = vi.fn();
  const result = browsing.restore("/manga", { left: 0, top: 3100 }, true).then(done);
  changed();
  expect(done).not.toHaveBeenCalled();
  document.body.innerHTML =
    '<main data-browse-route="/manga"><div data-browse-loading="true"></div></main>';
  changed();
  expect(done).not.toHaveBeenCalled();
  document.querySelector("[data-browse-loading]")!.removeAttribute("data-browse-loading");
  changed();
  await result;
  expect(done).toHaveBeenCalledWith({ left: 0, top: 3100 });
});
it("waits for root loaders and clamps a shorter or emptied list", async () => {
  document.body.innerHTML = '<main data-browse-route="/manga" data-browse-loading="true"></main>';
  vi.spyOn(document.documentElement, "scrollHeight", "get").mockReturnValue(1000);
  const browsing = createBrowseScroll();
  const result = browsing.restore("/manga", { left: 0, top: 3100 }, true);
  changed();
  document.querySelector("main")!.removeAttribute("data-browse-loading");
  changed();
  expect(await result).toEqual({ left: 0, top: 200 });
});
it.each(["wheel", "touchstart"])(
  "respects user %s input while restoration is pending",
  async (type) => {
    const browsing = createBrowseScroll();
    const result = browsing.restore("/missing", { left: 0, top: 3100 }, true);
    window.dispatchEvent(new Event(type));
    expect(await result).toBe(false);
    browsing.cancel();
  },
);
it("cancels an obsolete navigation and bounds waiting for failed pages", async () => {
  const browsing = createBrowseScroll();
  const old = browsing.restore("/missing", { left: 0, top: 2000 }, true);
  const fresh = browsing.restore("/manga", null, false);
  expect(await old).toBe(false);
  expect(await fresh).toEqual({ left: 0, top: 0 });
  const timeout = browsing.restore("/missing", { left: 0, top: 9000 }, true);
  await vi.advanceTimersByTimeAsync(10000);
  expect(await timeout).toEqual({ left: 0, top: 5200 });
});
