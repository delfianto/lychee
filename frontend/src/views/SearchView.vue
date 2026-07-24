<script setup lang="ts">
import { Search } from "lucide-vue-next";
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import SeriesCollection from "../components/SeriesCollection.vue";
import { librarySeries } from "../mocks/library";

const route = useRoute();
const router = useRouter();
const q = ref(String(route.query.q ?? ""));

// Reflect deep-links / navbar submits into the local field.
watch(
  () => route.query.q,
  (val) => {
    q.value = String(val ?? "");
  },
);

const results = computed(() => {
  const term = q.value.trim().toLowerCase();
  if (!term) return [];
  return librarySeries.filter(
    (s) => s.title.toLowerCase().includes(term) || s.authors.some((a) => a.toLowerCase().includes(term)),
  );
});

function submit(): void {
  const term = q.value.trim();
  void router.replace({ path: "/search", query: term ? { q: term } : {} });
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
        @keyup.enter="submit"
      />
    </label>

    <template v-if="q.trim()">
      <p class="text-sm text-base-content/60">
        {{ results.length }} result{{ results.length === 1 ? "" : "s" }} for “{{ q.trim() }}”
      </p>
      <SeriesCollection :series="results" density="list" empty-text="No series match your search." />
    </template>
    <div v-else class="py-16 text-center text-base-content/50">Type to search your whole library.</div>
  </div>
</template>
