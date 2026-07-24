<script setup lang="ts">
import { Grid2x2, LayoutGrid, List } from "lucide-vue-next";
import { type Component, computed, ref, watch } from "vue";

import SegmentedToggle from "../components/SegmentedToggle.vue";
import SeriesCollection from "../components/SeriesCollection.vue";
import { sortSeries } from "../lib/sort";
import { recentlyAdded } from "../mocks/library";

type Density = "list" | "compact" | "gallery";
const DENSITY_KEY = "lychee.density";
const stored = localStorage.getItem(DENSITY_KEY);
const density = ref<Density>(stored === "compact" || stored === "gallery" ? stored : "list");
watch(density, (d) => localStorage.setItem(DENSITY_KEY, d));
const densities: { value: Density; icon: Component; label: string }[] = [
  { value: "list", icon: List, label: "List view" },
  { value: "compact", icon: Grid2x2, label: "Compact view" },
  { value: "gallery", icon: LayoutGrid, label: "Gallery view" },
];

const sorts = ["Recently Added", "Rating", "Title"];
const sort = ref("Recently Added");
const sorted = computed(() => sortSeries(recentlyAdded, sort.value));
</script>

<template>
  <div class="flex flex-col gap-4 p-4 sm:p-6">
    <div class="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 class="text-3xl font-bold">Recently added</h1>
        <p class="text-sm text-base-content/60">{{ recentlyAdded.length }} series</p>
      </div>
      <div class="flex items-center gap-3">
        <SegmentedToggle v-model="density" :options="densities" aria-label="View density" />
        <label class="flex items-center gap-2 whitespace-nowrap text-xs text-base-content/60">
          Sort by
          <select v-model="sort" class="select select-bordered select-sm w-44">
            <option v-for="s in sorts" :key="s">{{ s }}</option>
          </select>
        </label>
      </div>
    </div>

    <SeriesCollection :series="sorted" :density="density" />
  </div>
</template>
