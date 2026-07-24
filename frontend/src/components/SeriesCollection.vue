<script setup lang="ts">
import { LoaderCircle } from "lucide-vue-next";
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";

import type { Series } from "../types";
import SeriesCoverCard from "./SeriesCoverCard.vue";
import SeriesListCard from "./SeriesListCard.vue";

// Renders a series list in the chosen density (list / compact / gallery) and
// reveals it in pages via infinite scroll. Shared by the library + the
// recently-added page so the grid + paging logic lives in one place.
const props = withDefaults(
  defineProps<{ series: Series[]; density: "list" | "compact" | "gallery"; emptyText?: string }>(),
  { emptyText: "Nothing here yet." },
);

const PAGE = 12;
const visibleCount = ref(PAGE);
const visible = computed(() => props.series.slice(0, visibleCount.value));
const hasMore = computed(() => visibleCount.value < props.series.length);
const loadingMore = ref(false);
const sentinel = ref<HTMLElement | null>(null);
const sentinelVisible = ref(false);
let timer: ReturnType<typeof setTimeout> | undefined;

function maybeLoadMore(): void {
  if (!sentinelVisible.value || !hasMore.value || loadingMore.value) return;
  loadingMore.value = true;
  timer = setTimeout(() => {
    visibleCount.value += PAGE;
    loadingMore.value = false;
  }, 180);
}
watch(loadingMore, (busy) => {
  if (!busy) maybeLoadMore();
});
watch(
  () => props.series,
  () => {
    visibleCount.value = PAGE;
  },
);

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
  <div class="flex flex-col gap-4">
    <div v-if="!series.length" class="py-16 text-center text-base-content/60">{{ emptyText }}</div>
    <div
      v-else-if="density === 'gallery'"
      class="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6"
    >
      <SeriesCoverCard v-for="s in visible" :key="s.id" :series="s" />
    </div>
    <div v-else-if="density === 'compact'" class="grid grid-cols-1 gap-3 xl:grid-cols-2">
      <SeriesListCard v-for="s in visible" :key="s.id" :series="s" compact />
    </div>
    <div v-else class="flex flex-col gap-3">
      <SeriesListCard v-for="s in visible" :key="s.id" :series="s" />
    </div>

    <div ref="sentinel" class="h-px w-full" aria-hidden="true"></div>
    <div v-if="loadingMore" class="flex justify-center py-4">
      <LoaderCircle class="size-6 animate-spin text-base-content/50" />
    </div>
  </div>
</template>
