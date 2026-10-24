<script setup lang="ts">
import { Search } from "@lucide/vue";
import { computed, onMounted, onUnmounted, ref, watch } from "vue";

import { onTaskDone } from "../api/events";
import type { LibraryRow } from "../api/client";
import { fetchLibraryRows } from "../api/settingsQueries";
import { createStaleGuard } from "../lib/staleGuard";
import ErrorState from "../components/ErrorState.vue";
import { fetchGalleries } from "../api/queries";
import SeriesCollection from "../components/SeriesCollection.vue";
import { sortSeries } from "../lib/sort";
import type { Series } from "../types";

defineOptions({ name: "GalleryView" });

// Fetch every cursor page across all galleries or within the selected library.
const names = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });
const libraries = ref<LibraryRow[]>([]);
const selectedLibrary = ref("");
const all = ref<Series[]>([]);
const loading = ref(true);
const loadError = ref("");
const loadGuard = createStaleGuard();

async function loadGalleries(): Promise<void> {
  const token = loadGuard.next();
  loading.value = true;
  loadError.value = "";
  all.value = [];
  try {
    const data = await fetchGalleries(selectedLibrary.value || undefined);
    if (loadGuard.isCurrent(token)) all.value = data;
  } catch (e) {
    if (loadGuard.isCurrent(token))
      loadError.value = e instanceof Error ? e.message : "Couldn’t load galleries";
  } finally {
    if (loadGuard.isCurrent(token)) loading.value = false;
  }
}
async function load(): Promise<void> {
  loading.value = true;
  loadError.value = "";
  try {
    libraries.value = (await fetchLibraryRows())
      .filter((library) => library.kind === "gallery")
      .sort((a, b) => names.compare(a.name, b.name) || a.id.localeCompare(b.id));
    if (
      selectedLibrary.value &&
      !libraries.value.some((library) => library.id === selectedLibrary.value)
    ) {
      selectedLibrary.value = "";
      return; // the selection watcher reloads all galleries
    }
    await loadGalleries();
  } catch (e) {
    loadError.value = e instanceof Error ? e.message : "Couldn’t load libraries";
    loading.value = false;
  }
}
watch(selectedLibrary, () => {
  artist.value = "";
  void loadGalleries();
});
onMounted(load);
onUnmounted(
  onTaskDone((task) => {
    if (task.kind === "scan") void load();
  }),
);

const query = ref("");
const artist = ref("");
const sort = ref("Recently Added");
const sorts = ["Recently Added", "Title", "Rating"];

const artists = computed(() =>
  [...new Set(all.value.flatMap((g) => g.artists))].sort(names.compare),
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
  return sortSeries(list, sort.value);
});
</script>

<template>
  <div class="flex flex-col gap-4 p-4 sm:p-6">
    <div>
      <h1 class="text-3xl font-bold">Gallery</h1>
      <p class="text-sm text-base-content/60">{{ filtered.length }} galleries</p>
    </div>

    <!-- Search includes series/franchise names; dropdowns stay limited to library and artist. -->
    <div class="flex flex-wrap items-center gap-2">
      <label class="input input-bordered input-sm flex w-full max-w-xs items-center gap-2">
        <Search class="size-4 opacity-60" />
        <input
          v-model="query"
          type="search"
          class="grow"
          placeholder="Search title, artist, series…"
          aria-label="Search galleries"
        />
      </label>
      <select
        v-if="libraries.length"
        v-model="selectedLibrary"
        class="select select-bordered select-sm w-40 max-w-full"
        aria-label="Gallery library"
      >
        <option value="">All galleries</option>
        <option v-for="library in libraries" :key="library.id" :value="library.id">
          {{ library.name }}
        </option>
      </select>
      <select
        v-model="artist"
        class="select select-bordered select-sm w-40 max-w-full"
        aria-label="Filter by artist"
      >
        <option value="">All artists</option>
        <option v-for="a in artists" :key="a">{{ a }}</option>
      </select>
      <label class="ml-auto flex items-center gap-2 whitespace-nowrap text-xs text-base-content/60">
        Sort by
        <select v-model="sort" class="select select-bordered select-sm w-40">
          <option v-for="s in sorts" :key="s">{{ s }}</option>
        </select>
      </label>
    </div>

    <!-- Always the large-image (gallery) density. -->
    <ErrorState v-if="loadError" :message="loadError" @retry="load" />
    <SeriesCollection
      v-else
      :series="filtered"
      density="gallery"
      :loading="loading"
      :empty-text="
        libraries.length
          ? 'No galleries match.'
          : 'No gallery libraries yet. Add one in Settings → Libraries.'
      "
    />
  </div>
</template>
