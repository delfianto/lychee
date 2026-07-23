<script setup lang="ts">
import type { Series } from "../types";
import SeriesCard from "./SeriesCard.vue";

withDefaults(defineProps<{ series: Series[]; loading?: boolean; skeletonCount?: number }>(), {
  loading: false,
  skeletonCount: 12,
});
</script>

<template>
  <div class="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
    <template v-if="loading">
      <div v-for="i in skeletonCount" :key="i" class="flex flex-col gap-2">
        <div class="skeleton cover w-full"></div>
        <div class="skeleton h-4 w-3/4"></div>
      </div>
    </template>
    <SeriesCard v-for="s in series" v-else :key="s.id" :series="s" />
  </div>
</template>
