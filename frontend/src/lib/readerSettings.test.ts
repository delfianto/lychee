import { beforeEach, describe, expect, it, vi } from "vite-plus/test";

const KEY = "lychee.reader";

beforeEach(() => {
  localStorage.clear();
  vi.resetModules(); // settings is a module-level singleton seeded once on import
});

describe("useReaderSettings load()", () => {
  it("falls back to defaults when nothing is stored", async () => {
    const { useReaderSettings } = await import("./readerSettings");
    expect(useReaderSettings()).toEqual({
      mode: "single",
      direction: "ltr",
      fit: "height",
      background: "dark",
      preloadPages: 4,
      videoAutoPlay: true,
      videoAutoNext: true,
    });
  });

  it("merges a stored partial value over the defaults and clamps preloadPages", async () => {
    localStorage.setItem(KEY, JSON.stringify({ mode: "double", fit: "width", preloadPages: 50 }));
    const { useReaderSettings, clampPreloadPages } = await import("./readerSettings");
    const settings = useReaderSettings();
    expect(settings.mode).toBe("double");
    expect(settings.fit).toBe("width");
    expect(settings.direction).toBe("ltr"); // untouched default
    expect(settings.preloadPages).toBe(20);
    expect(clampPreloadPages("invalid")).toBe(4);
    expect(clampPreloadPages(0)).toBe(1);
  });

  it("falls back to defaults (without throwing) on malformed JSON", async () => {
    localStorage.setItem(KEY, "{not valid json");
    const { useReaderSettings } = await import("./readerSettings");
    expect(useReaderSettings()).toEqual({
      mode: "single",
      direction: "ltr",
      fit: "height",
      background: "dark",
      preloadPages: 4,
      videoAutoPlay: true,
      videoAutoNext: true,
    });
  });

  it("persists changes back to localStorage", async () => {
    const { useReaderSettings } = await import("./readerSettings");
    useReaderSettings().mode = "longstrip";
    await new Promise((resolve) => setTimeout(resolve, 0)); // the watcher is async (flush: default "pre")
    expect(JSON.parse(localStorage.getItem(KEY) ?? "{}")).toMatchObject({ mode: "longstrip" });
  });
});
