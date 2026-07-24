<script setup lang="ts">
import { Search, X } from "lucide-vue-next";
import { computed, reactive } from "vue";

import FilterPanel from "../components/FilterPanel.vue";
import SeriesGrid from "../components/SeriesGrid.vue";
import { allBrowseTags, librarySeries } from "../mocks/library";
import type { BrowseFilters } from "../types";

const filters = reactive<BrowseFilters>({
  query: "",
  tags: {},
  tagMode: "and",
  ratings: new Set(),
  demographics: new Set(),
  statuses: new Set(),
  readStates: new Set(),
  sort: "Best match",
});

const sorts = ["Best match", "Title", "Recently added", "Recently updated", "Rating", "Unread"];

// Mock filtering: only the text query is wired; facets drive the UI + active chips
// until the real /api/series endpoint (ADR 10/17) is connected.
const results = computed(() =>
  librarySeries.filter((s) => s.title.toLowerCase().includes(filters.query.toLowerCase())),
);

const tagName = (id: string): string => allBrowseTags.find((t) => t.id === id)?.name ?? id;

const activeChips = computed(() => {
  const chips: { key: string; label: string; remove: () => void }[] = [];
  for (const [id, state] of Object.entries(filters.tags)) {
    chips.push({
      key: `t-${id}`,
      label: `${state === "exclude" ? "− " : "+ "}${tagName(id)}`,
      remove: () => delete filters.tags[id],
    });
  }
  for (const r of filters.ratings) chips.push({ key: `r-${r}`, label: r, remove: () => filters.ratings.delete(r) });
  for (const d of filters.demographics) chips.push({ key: `d-${d}`, label: d, remove: () => filters.demographics.delete(d) });
  for (const s of filters.statuses) chips.push({ key: `s-${s}`, label: s, remove: () => filters.statuses.delete(s) });
  for (const rs of filters.readStates) chips.push({ key: `rs-${rs}`, label: rs, remove: () => filters.readStates.delete(rs) });
  return chips;
});
</script>

<template>
  <div class="flex flex-col gap-4 p-4 sm:p-6">
    <!-- Toolbar -->
    <div class="flex flex-wrap items-center gap-2">
      <label class="input input-bordered input-sm flex grow items-center gap-2">
        <Search class="size-4 opacity-60" />
        <input v-model="filters.query" type="search" class="grow" placeholder="Search title or author…" />
      </label>
      <select v-model="filters.sort" class="select select-bordered select-sm">
        <option v-for="s in sorts" :key="s">{{ s }}</option>
      </select>
    </div>

    <div class="flex flex-col gap-4 lg:flex-row">
      <aside class="shrink-0 lg:w-64">
        <FilterPanel :filters="filters" />
      </aside>

      <div class="flex min-w-0 grow flex-col gap-3">
        <div class="flex flex-wrap items-center gap-2">
          <span class="text-sm text-base-content/70">{{ results.length }} results</span>
          <button
            v-for="c in activeChips"
            :key="c.key"
            class="badge badge-sm gap-1 capitalize"
            @click="c.remove()"
          >
            {{ c.label }}<X class="size-3" />
          </button>
        </div>

        <SeriesGrid v-if="results.length" :series="results" />
        <div
          v-else
          class="flex flex-col items-center justify-center gap-2 py-16 text-center text-base-content/60"
        >
          <Search class="size-10 opacity-40" />
          <p>No results found.</p>
        </div>
      </div>
    </div>
  </div>
</template>
