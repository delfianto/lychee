// Shared "default view" preferences: library density and the Lists page's
// default kind tab. Both used to be re-implemented as component-local refs
// seeded once from localStorage in every consumer, so changing one in
// Settings → Appearance had no effect on an already-mounted view. Reactive
// singletons (same shape as lib/fontSize.ts) fix that.

import { ref, watch } from "vue";

export type Density = "list" | "compact" | "gallery";
const DENSITY_KEY = "lychee.density";
function toDensity(v: string | null): Density {
  return v === "compact" || v === "gallery" ? v : "list";
}
const density = ref<Density>(toDensity(localStorage.getItem(DENSITY_KEY)));
watch(density, (d) => localStorage.setItem(DENSITY_KEY, d));

/** Live, two-way shared setting — any consumer changing it updates every other. */
export function useDensity() {
  return { density };
}

export type ListsTab = "all" | "manga" | "comic" | "gallery";
const LISTS_TAB_KEY = "lychee.listsDefaultTab";
function toListsTab(v: string | null): ListsTab {
  return v === "manga" || v === "comic" || v === "gallery" || v === "all" ? v : "manga";
}
const listsDefaultTab = ref<ListsTab>(toListsTab(localStorage.getItem(LISTS_TAB_KEY)));
watch(listsDefaultTab, (t) => localStorage.setItem(LISTS_TAB_KEY, t));

/** The persisted *default* — ListsView seeds its own current-tab state from this
 *  and reacts to later changes, but its own tab clicks don't write back here
 *  (only Settings sets the default). */
export function useListsDefaultTab() {
  return { listsDefaultTab };
}

export type RecentlyAddedKind = "manga" | "comic" | "gallery";
export const RECENTLY_ADDED_OPTIONS: { value: RecentlyAddedKind; label: string }[] = [
  { value: "manga", label: "Manga" },
  { value: "comic", label: "Comics" },
  { value: "gallery", label: "Gallery" },
];
const RECENTLY_ADDED_KEY = "lychee.recentlyAddedKinds";
const VALID_RECENTLY_ADDED_KINDS: RecentlyAddedKind[] = ["manga", "comic", "gallery"];

function normalizeRecentlyAddedKind(v: unknown): RecentlyAddedKind | null {
  if (v === "comics") return "comic";
  return v === "manga" || v === "comic" || v === "gallery" ? v : null;
}

function toRecentlyAddedKinds(raw: string | null): RecentlyAddedKind[] {
  if (raw === null) return ["manga"];
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return ["manga"];
    if (parsed.length === 0) return [];
    const normalized = new Set(
      parsed.map(normalizeRecentlyAddedKind).filter((k): k is RecentlyAddedKind => k !== null),
    );
    return normalized.size > 0
      ? VALID_RECENTLY_ADDED_KINDS.filter((k) => normalized.has(k))
      : ["manga"];
  } catch {
    const parts = raw
      .split(",")
      .map((s) => normalizeRecentlyAddedKind(s.trim()))
      .filter((k): k is RecentlyAddedKind => k !== null);
    return parts.length > 0
      ? VALID_RECENTLY_ADDED_KINDS.filter((k) => parts.includes(k))
      : ["manga"];
  }
}

const recentlyAddedKinds = ref<RecentlyAddedKind[]>(
  toRecentlyAddedKinds(localStorage.getItem(RECENTLY_ADDED_KEY)),
);
watch(
  recentlyAddedKinds,
  (kinds) => localStorage.setItem(RECENTLY_ADDED_KEY, JSON.stringify(kinds)),
  { deep: true },
);

export function toggleRecentlyAddedKind(kind: RecentlyAddedKind): void {
  const current = new Set(recentlyAddedKinds.value);
  if (current.has(kind)) current.delete(kind);
  else current.add(kind);
  recentlyAddedKinds.value = VALID_RECENTLY_ADDED_KINDS.filter((k) => current.has(k));
}

export function useRecentlyAddedKinds() {
  return { recentlyAddedKinds, toggleRecentlyAddedKind };
}

export interface MainBarIcons {
  comics: boolean;
  gallery: boolean;
}
const MAIN_BAR_KEY = "lychee.mainBarIcons";
const defaultMainBarIcons: MainBarIcons = { comics: true, gallery: true };

function toMainBarIcons(raw: string | null): MainBarIcons {
  if (!raw) return { ...defaultMainBarIcons };
  try {
    const parsed = JSON.parse(raw) as Partial<MainBarIcons>;
    return {
      comics: typeof parsed.comics === "boolean" ? parsed.comics : true,
      gallery: typeof parsed.gallery === "boolean" ? parsed.gallery : true,
    };
  } catch {
    return { ...defaultMainBarIcons };
  }
}

const mainBarIcons = ref<MainBarIcons>(toMainBarIcons(localStorage.getItem(MAIN_BAR_KEY)));
watch(mainBarIcons, (val) => localStorage.setItem(MAIN_BAR_KEY, JSON.stringify(val)), {
  deep: true,
});

export function useMainBarIcons() {
  return { mainBarIcons };
}
