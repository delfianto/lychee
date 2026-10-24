<script setup lang="ts">
import { Search } from "@lucide/vue";
import { onBeforeUnmount, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import CreatorInput from "../components/CreatorInput.vue";
import { searchSeries } from "../api/queries";
import SeriesCollection from "../components/SeriesCollection.vue";
import type { Series } from "../types";
import { createStaleGuard } from "../lib/staleGuard";

defineOptions({ name: "SearchView" });

const route = useRoute();
const router = useRouter();
const q = ref(String(route.query.q ?? ""));
const author = ref(String(route.query.author ?? ""));
const artist = ref(String(route.query.artist ?? ""));
const results = ref<Series[]>([]);
watch(
  () => [route.query.author, route.query.artist],
  ([a, b]) => {
    author.value = String(a ?? "");
    artist.value = String(b ?? "");
  },
);
const loading = ref(false);

// Reflect deep-links / navbar submits into the local field.
watch(
  () => route.query.q,
  (val) => {
    q.value = String(val ?? "");
  },
);

// Debounced live search against the API.
let timer: ReturnType<typeof setTimeout> | undefined;
const staleGuard = createStaleGuard();
watch(
  [q, author, artist],
  ([val]) => {
    const token = staleGuard.next();
    if (timer) clearTimeout(timer);
    const term = val.trim();
    if (!term && !author.value.trim() && !artist.value.trim()) {
      results.value = [];
      loading.value = false;
      return;
    }
    loading.value = true;
    timer = setTimeout(async () => {
      const found = await searchSeries(term, {
        ...(author.value.trim() ? { author: author.value.trim() } : {}),
        ...(artist.value.trim() ? { artist: artist.value.trim() } : {}),
      });
      if (!staleGuard.isCurrent(token)) return;
      results.value = found;
      loading.value = false;
    }, 250);
  },
  { immediate: true },
);

onBeforeUnmount(() => {
  clearTimeout(timer);
  staleGuard.next();
});

function submit(): void {
  const term = q.value.trim();
  void router.replace({
    path: "/search",
    query: {
      ...(term ? { q: term } : {}),
      ...(author.value ? { author: author.value } : {}),
      ...(artist.value ? { artist: artist.value } : {}),
    },
  });
}
</script>

<template>
  <div class="flex flex-col gap-4 p-4 sm:p-6">
    <h1 class="text-3xl font-bold">Search</h1>
    <label class="input input-bordered flex max-w-xl items-center gap-2">
      <Search class="size-4 opacity-60" />
      <input
        v-model="q"
        type="search"
        class="grow"
        placeholder="Search all series by title or author…"
        aria-label="Search all series"
        @keyup.enter="submit"
      />
    </label>

    <details :open="!!(author || artist)" class="rounded-box bg-base-100 p-4">
      <summary class="cursor-pointer text-sm font-semibold">Advanced search</summary>
      <div class="mt-3 grid max-w-2xl gap-4 sm:grid-cols-2">
        <CreatorInput v-model="author" role="author" /><CreatorInput
          v-model="artist"
          role="artist"
        />
      </div>
    </details>
    <template v-if="q.trim() || author.trim() || artist.trim()">
      <p class="text-sm text-base-content/60">
        <template v-if="loading">Searching…</template>
        <template v-else>
          {{ results.length }} result{{ results.length === 1 ? "" : "s"
          }}<template v-if="q.trim()"> for “{{ q.trim() }}”</template>
        </template>
      </p>
      <SeriesCollection
        :series="results"
        density="list"
        :loading="loading"
        empty-text="No series match your search."
      />
    </template>
    <div v-else class="py-16 text-center text-base-content/50">
      Type to search your whole library.
    </div>
  </div>
</template>
