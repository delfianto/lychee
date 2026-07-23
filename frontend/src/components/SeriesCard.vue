<script setup lang="ts">
import { RouterLink } from "vue-router";

import type { Series } from "../types";

defineProps<{ series: Series }>();
</script>

<template>
  <RouterLink :to="`/series/${series.id}`" class="group block">
    <div class="card bg-base-100 shadow-sm transition hover:shadow-md">
      <figure class="relative">
        <img :src="series.coverUrl" :alt="series.title" class="cover w-full rounded-t-box object-cover" />
        <span
          v-if="series.unreadCount > 0"
          class="badge badge-primary badge-sm absolute right-1 top-1"
        >
          {{ series.unreadCount }}
        </span>
      </figure>
      <div class="card-body gap-1 p-2">
        <h3 class="line-clamp-2 text-sm font-medium leading-tight">{{ series.title }}</h3>
        <p class="text-xs text-base-content/60">{{ series.chapterCount }} ch</p>
      </div>
    </div>
  </RouterLink>
</template>
