<script setup lang="ts">
import { Search } from "lucide-vue-next";
import { computed, ref } from "vue";

import SeriesCollection from "../components/SeriesCollection.vue";
import { sortSeries } from "../lib/sort";
import { libraryFor } from "../mocks/library";

// Galleries are image sets, not chaptered reading — so this page is deliberately
// different from the manga/comics library: always a large-image grid (no density
// toggle), no shelf-status tabs or filter presets, and filtering by the things
// that matter for artwork — artist/model and source series.
const all = computed(() => libraryFor("gallery").series);

const query = ref("");
const artist = ref("");
const source = ref("");
const sort = ref("Recently Added");
const sorts = ["Recently Added", "Title", "Rating"];

const artists = computed(() => [...new Set(all.value.flatMap((g) => g.artists))].sort());
const sources = computed(() =>
  [...new Set(all.value.map((g) => g.source).filter((s): s is string => Boolean(s)))].sort(),
);

const filtered = computed(() => {
  let list = all.value;
  const q = query.value.trim().toLowerCase();
  if (q)
    list = list.filter(
      (g) =>
        g.title.toLowerCase().includes(q) ||
        g.artists.some((a) => a.toLowerCase().includes(q)) ||
        (g.characters ?? []).some((c) => c.toLowerCase().includes(q)) ||
        (g.source ?? "").toLowerCase().includes(q),
    );
  if (artist.value) list = list.filter((g) => g.artists.includes(artist.value));
  if (source.value) list = list.filter((g) => g.source === source.value);
  return sortSeries(list, sort.value);
});
</script>

<template>
  <div class="flex flex-col gap-4 p-4 sm:p-6">
    <div>
      <h1 class="text-3xl font-bold">Gallery</h1>
      <p class="text-sm text-base-content/60">{{ filtered.length }} galleries</p>
    </div>

    <!-- Gallery-specific toolbar: search + artist / series filters + sort -->
    <div class="flex flex-wrap items-center gap-2">
      <label class="input input-bordered input-sm flex w-full max-w-xs items-center gap-2">
        <Search class="size-4 opacity-60" />
        <input v-model="query" type="search" class="grow" placeholder="Search title, artist, character…" />
      </label>
      <select v-model="artist" class="select select-bordered select-sm" aria-label="Filter by artist">
        <option value="">All artists</option>
        <option v-for="a in artists" :key="a">{{ a }}</option>
      </select>
      <select v-model="source" class="select select-bordered select-sm" aria-label="Filter by series">
        <option value="">All series</option>
        <option v-for="s in sources" :key="s">{{ s }}</option>
      </select>
      <label class="ml-auto flex items-center gap-2 whitespace-nowrap text-xs text-base-content/60">
        Sort by
        <select v-model="sort" class="select select-bordered select-sm w-40">
          <option v-for="s in sorts" :key="s">{{ s }}</option>
        </select>
      </label>
    </div>

    <!-- Always the large-image (gallery) density. -->
    <SeriesCollection :series="filtered" density="gallery" empty-text="No galleries match." />
  </div>
</template>
