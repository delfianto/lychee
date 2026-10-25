import { computed, ref, watch } from "vue";
import { defineStore } from "pinia";

export const HOME_SECTIONS = [
  { id: "continueReading", title: "Continue reading" },
  { id: "recentUpdates", title: "Recent updates" },
  { id: "rediscover", title: "Rediscover your library" },
  { id: "quickReads", title: "Quick reads" },
  { id: "readingList", title: "On your reading list" },
  { id: "recentlyAdded", title: "Recently added" },
] as const;
export type HomeSection = (typeof HOME_SECTIONS)[number]["id"];
export type HomePin =
  | { id: string; type: "list"; collectionId: string }
  | { id: string; type: "filter"; name: string; libraryKey: "manga" | "comics" };

interface Preferences {
  order: string[];
  hidden: string[];
  pins: HomePin[];
  discoveryKind: "manga" | "comic";
  following: boolean;
  shuffle: number;
  day: string;
}
const KEY = "lychee.home";
const today = () => new Date().toISOString().slice(0, 10);
function defaults(): Preferences {
  return {
    order: HOME_SECTIONS.map((s) => s.id),
    hidden: [],
    pins: [],
    discoveryKind: "manga",
    following: true,
    shuffle: 0,
    day: today(),
  };
}
function load(): Preferences {
  const fallback = defaults();
  try {
    const value = JSON.parse(localStorage.getItem(KEY) ?? "null") as Partial<Preferences> | null;
    if (!value || typeof value !== "object") return fallback;
    const pins = Array.isArray(value.pins)
      ? value.pins.filter(
          (p): p is HomePin =>
            !!p &&
            typeof p.id === "string" &&
            ((p.type === "list" &&
              typeof p.collectionId === "string" &&
              p.id === `list:${p.collectionId}`) ||
              (p.type === "filter" &&
                typeof p.name === "string" &&
                (p.libraryKey === "manga" || p.libraryKey === "comics") &&
                p.id === `filter:${p.libraryKey}:${p.name}`)),
        )
      : [];
    const known = new Set([...fallback.order, ...pins.map((p) => p.id)]);
    const order = Array.isArray(value.order)
      ? [...new Set(value.order.filter((id) => known.has(id)))]
      : [];
    return {
      ...fallback,
      pins,
      order: [...order, ...known].filter((id, index, all) => all.indexOf(id) === index),
      hidden: Array.isArray(value.hidden) ? value.hidden.filter((id) => known.has(id)) : [],
      discoveryKind: value.discoveryKind === "comic" ? "comic" : "manga",
      following: value.following !== false,
      shuffle:
        value.day === today() && Number.isSafeInteger(value.shuffle) && value.shuffle! >= 0
          ? value.shuffle!
          : 0,
    };
  } catch {
    return fallback;
  }
}

export const useHome = defineStore("home", () => {
  const preferences = ref(load());
  watch(preferences, (value) => localStorage.setItem(KEY, JSON.stringify(value)), { deep: true });
  const seed = computed(() => `${preferences.value.day}:${preferences.value.shuffle}`);
  function refreshDay(): boolean {
    if (preferences.value.day === today()) return false;
    preferences.value.day = today();
    preferences.value.shuffle = 0;
    return true;
  }
  function shuffle(): void {
    refreshDay();
    preferences.value.shuffle += 1;
  }
  function visible(id: string): boolean {
    return !preferences.value.hidden.includes(id);
  }
  function toggle(id: string): void {
    preferences.value.hidden = visible(id)
      ? [...preferences.value.hidden, id]
      : preferences.value.hidden.filter((key) => key !== id);
  }
  function move(id: string, direction: -1 | 1): void {
    const order = preferences.value.order;
    const index = order.indexOf(id),
      destination = index + direction;
    if (index < 0 || destination < 0 || destination >= order.length) return;
    [order[index], order[destination]] = [order[destination]!, order[index]!];
  }
  function unpin(id: string): void {
    preferences.value.pins = preferences.value.pins.filter((pin) => pin.id !== id);
    preferences.value.order = preferences.value.order.filter((key) => key !== id);
    preferences.value.hidden = preferences.value.hidden.filter((key) => key !== id);
  }
  function pin(value: HomePin): void {
    if (preferences.value.pins.some((p) => p.id === value.id)) {
      unpin(value.id);
      return;
    }
    preferences.value.pins.push(value);
    preferences.value.order.push(value.id);
  }
  function reset(): void {
    preferences.value = defaults();
  }
  return { preferences, seed, refreshDay, shuffle, visible, toggle, move, pin, unpin, reset };
});
