import { afterEach, beforeEach, describe, expect, it, vi } from "vite-plus/test";
import { nextTick } from "vue";

beforeEach(() => {
  vi.resetModules();
  localStorage.clear();
});
afterEach(() => {
  vi.useRealTimers();
  document.documentElement.removeAttribute("data-theme");
  document.documentElement.style.fontSize = "";
});

describe("shared display preferences", () => {
  it.each(["compact", "gallery", "list", "invalid"])(
    "loads density %s and shares subsequent changes",
    async (stored) => {
      localStorage.setItem("lychee.density", stored);
      const preferences = await import("./density");
      const first = preferences.useDensity();
      expect(first.density.value).toBe(stored === "invalid" ? "list" : stored);
      first.density.value = "gallery";
      await nextTick();
      expect(preferences.useDensity().density.value).toBe("gallery");
      expect(localStorage.getItem("lychee.density")).toBe("gallery");
    },
  );

  it.each(["all", "manga", "comic", "gallery", "invalid"])(
    "loads the lists default %s and persists changes",
    async (stored) => {
      localStorage.setItem("lychee.listsDefaultTab", stored);
      const { useListsDefaultTab } = await import("./density");
      const { listsDefaultTab } = useListsDefaultTab();
      expect(listsDefaultTab.value).toBe(stored === "invalid" ? "manga" : stored);
      listsDefaultTab.value = "all";
      await nextTick();
      expect(localStorage.getItem("lychee.listsDefaultTab")).toBe("all");
    },
  );

  it.each([
    [null, ["manga"]],
    ['["gallery","comics"]', ["comic", "gallery"]],
    ["manga,gallery", ["manga", "gallery"]],
    ["invalid", ["manga"]],
    ['["invalid"]', ["manga"]],
    ["123", ["manga"]],
    ["[]", []],
  ])(
    "loads recentlyAddedKinds %s and toggles kinds in canonical order",
    async (stored, expected) => {
      if (stored !== null) localStorage.setItem("lychee.recentlyAddedKinds", stored);
      const { useRecentlyAddedKinds } = await import("./density");
      const { recentlyAddedKinds, toggleRecentlyAddedKind } = useRecentlyAddedKinds();
      expect(recentlyAddedKinds.value).toEqual(expected);
      toggleRecentlyAddedKind("comic");
      await nextTick();
      expect(JSON.parse(localStorage.getItem("lychee.recentlyAddedKinds") ?? "[]")).toEqual(
        recentlyAddedKinds.value,
      );
    },
  );

  it.each([
    [null, { comics: true, gallery: true, lists: true }],
    ['{"comics":false,"gallery":true}', { comics: false, gallery: true, lists: true }],
    ['{"comics":"bad"}', { comics: true, gallery: true, lists: true }],
    ["invalid", { comics: true, gallery: true, lists: true }],
    ['{"lists":false}', { comics: true, gallery: true, lists: false }],
    ['{"lists":"bad"}', { comics: true, gallery: true, lists: true }],
  ])("loads mainBarIcons %s and persists changes", async (stored, expected) => {
    if (stored !== null) localStorage.setItem("lychee.mainBarIcons", stored);
    const { useMainBarIcons } = await import("./density");
    const { mainBarIcons } = useMainBarIcons();
    expect(mainBarIcons.value).toEqual(expected);
    mainBarIcons.value.comics = false;
    mainBarIcons.value.lists = !expected.lists;
    await nextTick();
    expect(JSON.parse(localStorage.getItem("lychee.mainBarIcons") ?? "{}")).toEqual({
      comics: false,
      gallery: expected.gallery,
      lists: !expected.lists,
    });
  });
});

describe("font size", () => {
  it.each([
    [null, 16],
    ["garbage", 16],
    ["100", 22],
    ["10", 14],
    ["18.6", 19],
  ])("restores %s safely", async (stored, expected) => {
    if (stored !== null) localStorage.setItem("lychee.fontSize", stored);
    const { useFontSize } = await import("./fontSize");
    expect(useFontSize().fontSize.value).toBe(expected);
    expect(document.documentElement.style.fontSize).toBe(`${expected}px`);
  });
  it("applies changes immediately, debounces persistence, and resets", async () => {
    vi.useFakeTimers();
    const { useFontSize } = await import("./fontSize");
    const { setFontSize, resetFontSize, fontSize } = useFontSize();
    setFontSize(18.6);
    expect(fontSize.value).toBe(19);
    expect(document.documentElement.style.fontSize).toBe("19px");
    vi.advanceTimersByTime(200);
    setFontSize(30);
    expect(localStorage.getItem("lychee.fontSize")).toBeNull();
    vi.advanceTimersByTime(249);
    expect(localStorage.getItem("lychee.fontSize")).toBeNull();
    vi.advanceTimersByTime(1);
    expect(localStorage.getItem("lychee.fontSize")).toBe("22");
    resetFontSize();
    vi.advanceTimersByTime(250);
    expect(localStorage.getItem("lychee.fontSize")).toBe("16");
  });
});

describe("theme", () => {
  it.each([
    [null, "dark"],
    ["unknown", "dark"],
    ["nord", "nord"],
  ])("restores stored theme %s", async (stored, expected) => {
    if (stored !== null) localStorage.setItem("lychee.theme", stored);
    const { useTheme } = await import("./theme");
    expect(useTheme().theme.value).toBe(expected);
    expect(document.documentElement.dataset.theme).toBe(expected);
  });
  it("keeps paired modes, storage, and the DOM in sync, ignoring unknown themes", async () => {
    const { useTheme } = await import("./theme");
    const first = useTheme();
    first.setTheme("nord");
    first.setMode("dark");
    expect(first.theme.value).toBe("nord");
    first.toggleMode();
    expect(first.theme.value).toBe("nord-light");
    expect(first.mode.value).toBe("light");
    first.setMode("dark");
    first.setTheme("does-not-exist");
    expect(useTheme().theme.value).toBe("nord");
    expect(localStorage.getItem("lychee.theme")).toBe("nord");
    expect(document.documentElement.dataset.theme).toBe("nord");
    for (const theme of first.THEMES) {
      const pair = first.THEMES.find((candidate) => candidate.id === theme.pair)!;
      expect(pair.pair).toBe(theme.id);
      expect(pair.mode).not.toBe(theme.mode);
    }
  });
});
