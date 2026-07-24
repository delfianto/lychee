<script setup lang="ts">
import { Grid2x2, LayoutGrid, List, Search, SlidersHorizontal, X } from "lucide-vue-next";
import { type Component, computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute } from "vue-router";

import { buildLibraryQuery, fetchTagGroups, type TagGroup, useSeriesList } from "../api/queries";
import FilterPanel from "../components/FilterPanel.vue";
import SegmentedToggle from "../components/SegmentedToggle.vue";
import SeriesCollection from "../components/SeriesCollection.vue";
import { toast } from "../lib/toast";
import type { BrowseFilters, ContentRating, Demographic, LibraryStatus, PublicationStatus } from "../types";

const props = defineProps<{ libraryKey: string }>();
const route = useRoute();

// --- Density -------------------------------------------------------------
type Density = "list" | "compact" | "gallery";
const DENSITY_KEY = "lychee.density";
function initialDensity(): Density {
  const q = route.query.view;
  if (q === "list" || q === "compact" || q === "gallery") return q;
  const stored = localStorage.getItem(DENSITY_KEY);
  return stored === "compact" || stored === "gallery" ? stored : "list";
}
const density = ref<Density>(initialDensity());
watch(density, (d) => localStorage.setItem(DENSITY_KEY, d));
const densities: { value: Density; icon: Component; label: string }[] = [
  { value: "list", icon: List, label: "List view" },
  { value: "compact", icon: Grid2x2, label: "Compact view" },
  { value: "gallery", icon: LayoutGrid, label: "Gallery view" },
];

// --- Shelf-status tabs + sort -------------------------------------------
const statusTabs: { value: LibraryStatus | "all"; label: string }[] = [
  { value: "all", label: "All" },
  { value: "reading", label: "Reading" },
  { value: "plan_to_read", label: "Plan to read" },
  { value: "on_hold", label: "On hold" },
  { value: "completed", label: "Completed" },
  { value: "dropped", label: "Dropped" },
  { value: "re_reading", label: "Re-reading" },
];
const activeTab = ref<LibraryStatus | "all">("all");
const sorts = ["Rating", "Recently Added", "Recently Updated", "Title", "Unread"];
const sort = ref("Recently Added");

// --- Advanced filters ----------------------------------------------------
const showFilters = ref(false);
const filters = reactive<BrowseFilters>({
  query: "",
  tags: {},
  tagMode: "and",
  ratings: new Set(),
  demographics: new Set(),
  statuses: new Set(),
  readStates: new Set(),
  sort: "",
});

function resetFilters(): void {
  filters.query = "";
  filters.tags = {};
  filters.ratings = new Set();
  filters.demographics = new Set();
  filters.statuses = new Set();
  filters.readStates = new Set();
}

const tagGroups = ref<TagGroup[]>([]);
onMounted(async () => {
  tagGroups.value = await fetchTagGroups();
});
function tagName(id: string): string {
  for (const group of tagGroups.value) {
    const tag = group.tags.find((t) => t.id === id);
    if (tag) return tag.name;
  }
  return id;
}

const activeChips = computed(() => {
  const chips: { key: string; label: string; remove: () => void }[] = [];
  if (filters.query) chips.push({ key: "q", label: `“${filters.query}”`, remove: () => (filters.query = "") });
  for (const [id, state] of Object.entries(filters.tags))
    chips.push({ key: `t-${id}`, label: `${state === "exclude" ? "−" : "+"} ${tagName(id)}`, remove: () => delete filters.tags[id] });
  for (const r of filters.ratings) chips.push({ key: `r-${r}`, label: r, remove: () => filters.ratings.delete(r) });
  for (const d of filters.demographics) chips.push({ key: `d-${d}`, label: d, remove: () => filters.demographics.delete(d) });
  for (const s of filters.statuses) chips.push({ key: `s-${s}`, label: s, remove: () => filters.statuses.delete(s) });
  for (const rs of filters.readStates) chips.push({ key: `rs-${rs}`, label: rs, remove: () => filters.readStates.delete(rs) });
  return chips;
});

// --- Presets (persisted, shared across libraries) ------------------------
interface Preset {
  name: string;
  query: string;
  tags: Record<string, "include" | "exclude">;
  tagMode: "and" | "or";
  ratings: ContentRating[];
  demographics: Demographic[];
  statuses: PublicationStatus[];
  readStates: string[];
}
const PRESETS_KEY = "lychee.presets";
function loadPresets(): Preset[] {
  try {
    return JSON.parse(localStorage.getItem(PRESETS_KEY) ?? "[]") as Preset[];
  } catch {
    return [];
  }
}
const presets = ref<Preset[]>(loadPresets());
const presetName = ref("");
function persistPresets(): void {
  localStorage.setItem(PRESETS_KEY, JSON.stringify(presets.value));
}
function savePreset(): void {
  const name = presetName.value.trim();
  if (!name) return;
  const p: Preset = {
    name,
    query: filters.query,
    tags: { ...filters.tags },
    tagMode: filters.tagMode,
    ratings: [...filters.ratings],
    demographics: [...filters.demographics],
    statuses: [...filters.statuses],
    readStates: [...filters.readStates],
  };
  const idx = presets.value.findIndex((x) => x.name === name);
  if (idx >= 0) presets.value[idx] = p;
  else presets.value.push(p);
  persistPresets();
  toast(`Saved preset “${name}”`);
  presetName.value = "";
}
function applyPreset(p: Preset): void {
  filters.query = p.query;
  filters.tags = { ...p.tags };
  filters.tagMode = p.tagMode;
  filters.ratings = new Set(p.ratings);
  filters.demographics = new Set(p.demographics);
  filters.statuses = new Set(p.statuses);
  filters.readStates = new Set(p.readStates);
}
function deletePreset(name: string): void {
  presets.value = presets.value.filter((p) => p.name !== name);
  persistPresets();
}

// --- Data (server-filtered + cursor-paginated) ---------------------------
const TITLES: Record<string, string> = {
  manga: "Manga",
  comics: "Comics",
  favorites: "Favorites",
  reading: "Reading",
  gallery: "Gallery",
};
const title = computed(() => TITLES[props.libraryKey] ?? "Library");
// "reading" is a fixed-status shelf, so the shelf-status tabs are hidden there.
const showTabs = computed(() => props.libraryKey !== "reading");

const { items: results, loading, hasMore, reload, loadMore } = useSeriesList();

const queryParams = computed(() =>
  buildLibraryQuery(props.libraryKey, { activeTab: activeTab.value, filters, sort: sort.value }),
);

// Refetch (debounced) whenever the library, tab, filters, or sort change.
let reloadTimer: ReturnType<typeof setTimeout> | undefined;
watch(
  queryParams,
  (q) => {
    if (reloadTimer) clearTimeout(reloadTimer);
    reloadTimer = setTimeout(() => void reload(q), 200);
  },
  { immediate: true },
);

// Reset tab + filters when switching libraries.
watch(
  () => props.libraryKey,
  () => {
    activeTab.value = "all";
    resetFilters();
  },
);
</script>

<template>
  <div class="flex flex-col gap-4 p-4 sm:p-6">
    <!-- Title -->
    <div>
      <h1 class="text-3xl font-bold">{{ title }}</h1>
      <p class="text-sm text-base-content/60">{{ results.length }} series</p>
    </div>

    <!-- Toolbar: search + filters · density + sort -->
    <div class="flex flex-wrap items-center gap-2">
      <label class="input input-bordered input-sm flex w-full max-w-xs items-center gap-2">
        <Search class="size-4 opacity-60" />
        <input v-model="filters.query" type="search" class="grow" placeholder="Search this library…" />
      </label>
      <button
        class="btn btn-sm gap-1.5"
        :class="showFilters || activeChips.length ? 'btn-primary' : 'btn-ghost surface-border'"
        @click="showFilters = !showFilters"
      >
        <SlidersHorizontal class="size-4" />Filters
        <span v-if="activeChips.length" class="badge badge-xs">{{ activeChips.length }}</span>
      </button>

      <div class="ml-auto flex items-center gap-3">
        <SegmentedToggle v-model="density" :options="densities" aria-label="View density" />
        <label class="flex items-center gap-2 whitespace-nowrap text-xs text-base-content/60">
          Sort by
          <select v-model="sort" class="select select-bordered select-sm w-44">
            <option v-for="s in sorts" :key="s">{{ s }}</option>
          </select>
        </label>
      </div>
    </div>

    <!-- Shelf-status tabs -->
    <div v-if="showTabs" role="tablist" class="tabs tabs-box max-w-full self-start overflow-x-auto surface-border">
      <a
        v-for="tab in statusTabs"
        :key="tab.value"
        role="tab"
        class="tab whitespace-nowrap"
        :class="{ 'tab-active': activeTab === tab.value }"
        @click="activeTab = tab.value"
      >
        {{ tab.label }}
      </a>
    </div>

    <!-- Saved presets -->
    <div v-if="presets.length" class="flex flex-wrap items-center gap-1.5">
      <span class="text-xs text-base-content/50">Presets</span>
      <span
        v-for="p in presets"
        :key="p.name"
        class="badge badge-outline cursor-pointer gap-1 hover:border-primary"
        @click="applyPreset(p)"
      >
        {{ p.name }}
        <button class="opacity-60 hover:opacity-100" aria-label="Delete preset" @click.stop="deletePreset(p.name)">
          <X class="size-3" />
        </button>
      </span>
    </div>

    <!-- Active-filter chips -->
    <div v-if="activeChips.length" class="flex flex-wrap items-center gap-1.5">
      <button
        v-for="c in activeChips"
        :key="c.key"
        class="badge badge-primary badge-sm gap-1 capitalize"
        @click="c.remove()"
      >
        {{ c.label }}<X class="size-3" />
      </button>
      <button class="btn btn-ghost btn-xs" @click="resetFilters">Clear all</button>
    </div>

    <!-- Foldable advanced filters -->
    <div v-if="showFilters" class="flex flex-col gap-4 rounded-box surface-border bg-base-100 p-4">
      <FilterPanel :filters="filters" :tag-groups="tagGroups" />
      <div class="divider my-0"></div>
      <div class="flex flex-wrap items-center gap-2">
        <span class="text-sm font-medium">Save as preset</span>
        <input
          v-model="presetName"
          type="text"
          placeholder="e.g. Unread Seinen"
          class="input input-bordered input-sm max-w-xs"
          @keyup.enter="savePreset"
        />
        <button class="btn btn-primary btn-sm" :disabled="!presetName.trim()" @click="savePreset">Save</button>
        <button class="btn btn-ghost btn-sm ml-auto" @click="resetFilters">Clear all filters</button>
      </div>
    </div>

    <!-- Results -->
    <SeriesCollection
      :series="results"
      :density="density"
      :has-more="hasMore"
      :loading="loading"
      empty-text="No series match these filters."
      @load-more="loadMore"
    />
  </div>
</template>
