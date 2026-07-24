<script setup lang="ts">
import { Grid2x2, LayoutGrid, List, LoaderCircle } from "lucide-vue-next";
import { type Component, computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";

import SeriesCoverCard from "../components/SeriesCoverCard.vue";
import SeriesListCard from "../components/SeriesListCard.vue";
import { libraryFor } from "../mocks/library";
import type { LibraryStatus } from "../types";

const props = defineProps<{ libraryKey: string }>();
const route = useRoute();

type Density = "list" | "compact" | "gallery";
const DENSITY_KEY = "lychee.density";

// Density comes from `?view=` (deep-link) if present, else the persisted choice, else list.
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

const lib = computed(() => libraryFor(props.libraryKey));
const filtered = computed(() =>
  activeTab.value === "all"
    ? lib.value.series
    : lib.value.series.filter((s) => s.libraryStatus === activeTab.value),
);

// --- Infinite scroll (client-side reveal over the mock list) ---------------
const PAGE = 12;
const visibleCount = ref(PAGE);
const visible = computed(() => filtered.value.slice(0, visibleCount.value));
const hasMore = computed(() => visibleCount.value < filtered.value.length);
const loadingMore = ref(false);
const sentinel = ref<HTMLElement | null>(null);
const sentinelVisible = ref(false);
let timer: ReturnType<typeof setTimeout> | undefined;

function maybeLoadMore(): void {
  if (!sentinelVisible.value || !hasMore.value || loadingMore.value) return;
  loadingMore.value = true;
  // Small delay so the spinner registers; a real API call replaces this later.
  timer = setTimeout(() => {
    visibleCount.value += PAGE;
    loadingMore.value = false;
  }, 180);
}

// Keep filling while the sentinel stays in view (short lists / fast scroll).
watch(loadingMore, (busy) => {
  if (!busy) maybeLoadMore();
});

// Reset paging (and tab) when the library or the active filter changes.
watch(
  () => props.libraryKey,
  () => {
    activeTab.value = "all";
    visibleCount.value = PAGE;
  },
);
watch(activeTab, () => {
  visibleCount.value = PAGE;
});

let observer: IntersectionObserver | null = null;
onMounted(() => {
  observer = new IntersectionObserver(
    ([entry]) => {
      sentinelVisible.value = entry?.isIntersecting ?? false;
      maybeLoadMore();
    },
    { rootMargin: "300px" },
  );
  if (sentinel.value) observer.observe(sentinel.value);
});
onBeforeUnmount(() => {
  observer?.disconnect();
  if (timer) clearTimeout(timer);
});
</script>

<template>
  <div class="flex flex-col gap-4 p-4 sm:p-6">
    <!-- Header + controls -->
    <div class="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 class="text-3xl font-bold">{{ lib.title }}</h1>
        <p class="text-sm text-base-content/60">{{ filtered.length }} series</p>
      </div>
      <div class="flex items-center gap-3">
        <div class="join">
          <button
            v-for="d in densities"
            :key="d.value"
            class="btn btn-sm join-item"
            :class="density === d.value ? 'btn-primary' : 'btn-ghost'"
            :aria-label="d.label"
            @click="density = d.value"
          >
            <component :is="d.icon" class="size-4" />
          </button>
        </div>
        <label class="flex items-center gap-2 whitespace-nowrap text-xs text-base-content/60">
          Sort by
          <select v-model="sort" class="select select-bordered select-sm w-44">
            <option v-for="s in sorts" :key="s">{{ s }}</option>
          </select>
        </label>
      </div>
    </div>

    <!-- Reading-status filter tabs -->
    <div role="tablist" class="tabs tabs-box max-w-full self-start overflow-x-auto">
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

    <!-- Body -->
    <div v-if="!filtered.length" class="py-16 text-center text-base-content/60">Nothing here yet.</div>
    <div
      v-else-if="density === 'gallery'"
      class="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5"
    >
      <SeriesCoverCard v-for="s in visible" :key="s.id" :series="s" />
    </div>
    <div v-else-if="density === 'compact'" class="grid grid-cols-1 gap-3 xl:grid-cols-2">
      <SeriesListCard v-for="s in visible" :key="s.id" :series="s" compact />
    </div>
    <div v-else class="flex flex-col gap-3">
      <SeriesListCard v-for="s in visible" :key="s.id" :series="s" />
    </div>

    <!-- Endless-scroll sentinel (fires ~300px early) + loading spinner -->
    <div ref="sentinel" class="h-px w-full" aria-hidden="true"></div>
    <div v-if="loadingMore" class="flex justify-center py-4">
      <LoaderCircle class="size-6 animate-spin text-base-content/50" />
    </div>
  </div>
</template>
