import { createPinia, disposePinia, setActivePinia, type Pinia } from "pinia";
import { nextTick } from "vue";
import { afterEach, expect, it } from "vite-plus/test";
import { HOME_SECTIONS, useHome } from "./home";
import { presetFilters, usePresets, type BrowsePreset } from "./presets";

const scopes: Pinia[] = [];
function fresh() {
  const pinia = createPinia();
  scopes.push(pinia);
  setActivePinia(pinia);
  return pinia;
}
afterEach(() => {
  scopes.splice(0).forEach(disposePinia);
});
const preset: BrowsePreset = {
  name: "Weekend",
  query: "story",
  tags: { action: "include", drama: "exclude" },
  tagMode: "or",
  author: "Writer",
  artist: "Artist",
  ratings: ["safe"],
  demographics: ["josei"],
  statuses: ["completed"],
  readStates: ["unread"],
};

it("persists section visibility/order, typed pins, discovery scope and shuffle", async () => {
  fresh();
  const home = useHome();
  expect(home.preferences.order).toEqual(HOME_SECTIONS.map((s) => s.id));
  home.toggle("readingList");
  expect(home.visible("readingList")).toBe(false);
  home.toggle("readingList");
  home.move("readingList", -1);
  home.move("readingList", 1);
  const original = [...home.preferences.order];
  home.move("continueReading", -1);
  home.move("recentlyAdded", 1);
  home.move("unknown", 1);
  expect(home.preferences.order).toEqual(original);
  home.pin({ id: "list:one", type: "list", collectionId: "one" });
  home.pin({ id: "filter:comics:Weekend", type: "filter", name: "Weekend", libraryKey: "comics" });
  home.toggle("list:one");
  home.unpin("list:one");
  expect(home.preferences.hidden).not.toContain("list:one");
  home.preferences.discoveryKind = "comic";
  home.preferences.following = false;
  const seed = home.seed;
  expect(home.refreshDay()).toBe(false);
  home.preferences.day = "2000-01-01";
  expect(home.refreshDay()).toBe(true);
  home.shuffle();
  expect(home.seed).not.toBe(seed);
  await nextTick();
  const saved = JSON.parse(localStorage.getItem("lychee.home")!);
  fresh();
  expect(useHome().preferences).toEqual(saved);
  useHome().pin({
    id: "filter:comics:Weekend",
    type: "filter",
    name: "Weekend",
    libraryKey: "comics",
  });
  expect(useHome().preferences.pins).toEqual([]);
  useHome().reset();
  expect(useHome().preferences.following).toBe(true);
  expect(useHome().preferences.discoveryKind).toBe("manga");
});

it("repairs stale/malformed Home preferences without losing valid pins", () => {
  for (const raw of [
    "{",
    "null",
    "7",
    JSON.stringify({}),
    JSON.stringify({ pins: "bad", order: 7, hidden: 9 }),
  ]) {
    localStorage.setItem("lychee.home", raw);
    fresh();
    expect(useHome().preferences.order).toHaveLength(6);
  }
  localStorage.setItem(
    "lychee.home",
    JSON.stringify({
      pins: [
        null,
        { id: "bad", type: "other" },
        { id: "list:ok", type: "list", collectionId: "ok" },
        { id: "filter:manga:Saved", type: "filter", name: "Saved", libraryKey: "manga" },
      ],
      order: ["quickReads", "quickReads", "unknown", "list:ok"],
      hidden: ["unknown", "quickReads"],
      discoveryKind: "gallery",
      day: "2000-01-01",
      shuffle: 5,
    }),
  );
  fresh();
  expect(useHome().preferences.pins).toHaveLength(2);
  expect(useHome().preferences.order.slice(0, 2)).toEqual(["quickReads", "list:ok"]);
  expect(useHome().preferences.hidden).toEqual(["quickReads"]);
  expect(useHome().preferences.shuffle).toBe(0);
});

it("shares editable presets with Home while retaining existing saved data", async () => {
  for (const raw of ["{", "7"]) {
    localStorage.setItem("lychee.presets", raw);
    fresh();
    expect(usePresets().presets).toEqual([]);
  }
  localStorage.setItem("lychee.presets", JSON.stringify([null, {}, preset]));
  fresh();
  const store = usePresets();
  expect(store.presets).toHaveLength(1);
  store.save({ ...preset, query: "changed" });
  store.save({ ...preset, name: "Second" });
  await nextTick();
  expect(JSON.parse(localStorage.getItem("lychee.presets")!)).toHaveLength(2);
  const converted = presetFilters(store.presets[0]!);
  expect(converted.query).toBe("changed");
  expect(converted.tags).toEqual(preset.tags);
  expect([...converted.demographics]).toEqual(["josei"]);
  expect(converted.author).toBe("Writer");
  expect(converted.tagMode).toBe("or");
  const sparse = presetFilters({ name: "Old" } as BrowsePreset);
  expect(sparse.query).toBe("");
  expect(sparse.artist).toBe("");
  expect(sparse.author).toBe("");
  expect(sparse.tagMode).toBe("and");
  store.remove("Weekend");
  expect(store.presets.map((p) => p.name)).toEqual(["Second"]);
});
