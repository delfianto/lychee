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
