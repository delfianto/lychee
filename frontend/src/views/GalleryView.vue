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

// Fetch and derive facets within the selected library, including every cursor page.
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
    const data = selectedLibrary.value ? await fetchGalleries(selectedLibrary.value) : [];
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
    libraries.value = (await fetchLibraryRows()).filter(
      (l) => l.kind === "gallery" || l.kind === "mixed",
    );
    if (!libraries.value.some((l) => l.id === selectedLibrary.value)) {
      selectedLibrary.value = libraries.value[0]?.id ?? "";
      if (selectedLibrary.value) return; // the selection watcher loads it
    }
    await loadGalleries();
  } catch (e) {
    loadError.value = e instanceof Error ? e.message : "Couldn’t load libraries";
    loading.value = false;
  }
}
watch(selectedLibrary, () => {
  artist.value = "";
  source.value = "";
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

    <label v-if="libraries.length" class="flex flex-wrap items-center gap-2 text-sm">
      Library
      <select
        v-model="selectedLibrary"
        class="select select-bordered select-sm w-full sm:w-72"
        aria-label="Gallery library"
      >
        <option v-for="library in libraries" :key="library.id" :value="library.id">
          {{ library.name }}
        </option>
      </select>
    </label>

    <!-- Gallery-specific toolbar: search + artist / series filters + sort -->
    <div class="flex flex-wrap items-center gap-2">
      <label class="input input-bordered input-sm flex w-full max-w-xs items-center gap-2">
        <Search class="size-4 opacity-60" />
        <input
          v-model="query"
          type="search"
          class="grow"
          placeholder="Search title, artist, character…"
          aria-label="Search galleries"
        />
      </label>
      <select
        v-model="artist"
        class="select select-bordered select-sm"
        aria-label="Filter by artist"
      >
        <option value="">All artists</option>
        <option v-for="a in artists" :key="a">{{ a }}</option>
      </select>
      <select
        v-model="source"
        class="select select-bordered select-sm"
        aria-label="Filter by series"
      >
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
