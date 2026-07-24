<script setup lang="ts">
import { LoaderCircle } from "lucide-vue-next";
import { onBeforeUnmount, onMounted, ref, watch } from "vue";

import type { Series } from "../types";
import SeriesCoverCard from "./SeriesCoverCard.vue";
import SeriesListCard from "./SeriesListCard.vue";

// Presentational grid in the chosen density (list / compact / gallery). Paging is
// server-driven: the parent owns the accumulated `series` + `hasMore`/`loading`
// and fetches the next page when we emit `loadMore` (near the scroll sentinel).
const props = withDefaults(
  defineProps<{
    series: Series[];
    density: "list" | "compact" | "gallery";
    emptyText?: string;
    hasMore?: boolean;
    loading?: boolean;
  }>(),
  { emptyText: "Nothing here yet.", hasMore: false, loading: false },
);
const emit = defineEmits<{ loadMore: [] }>();

const sentinel = ref<HTMLElement | null>(null);
const sentinelVisible = ref(false);

function maybeLoadMore(): void {
  if (sentinelVisible.value && props.hasMore && !props.loading) emit("loadMore");
}

// After a page finishes loading, keep going if the sentinel is still on screen.
watch(() => props.loading, (busy) => {
  if (!busy) maybeLoadMore();
});

let observer: IntersectionObserver | null = null;
onMounted(() => {
  observer = new IntersectionObserver(
    ([entry]) => {
      sentinelVisible.value = entry?.isIntersecting ?? false;
      maybeLoadMore();
    },
    { rootMargin: "400px" },
  );
  if (sentinel.value) observer.observe(sentinel.value);
});
onBeforeUnmount(() => observer?.disconnect());
</script>

<template>
  <div class="flex flex-col gap-4">
    <div v-if="!series.length && !loading" class="py-16 text-center text-base-content/60">
      {{ emptyText }}
    </div>
    <div
      v-else-if="density === 'gallery'"
      class="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6"
    >
      <SeriesCoverCard v-for="s in series" :key="s.id" :series="s" />
    </div>
    <div v-else-if="density === 'compact'" class="grid grid-cols-1 gap-3 xl:grid-cols-2">
      <SeriesListCard v-for="s in series" :key="s.id" :series="s" compact />
    </div>
    <div v-else class="flex flex-col gap-3">
      <SeriesListCard v-for="s in series" :key="s.id" :series="s" />
    </div>

    <div ref="sentinel" class="h-px w-full" aria-hidden="true"></div>
    <div v-if="loading" class="flex justify-center py-4">
      <LoaderCircle class="size-6 animate-spin text-base-content/50" />
    </div>
  </div>
</template>
