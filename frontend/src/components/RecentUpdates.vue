<script setup lang="ts">
import { RouterLink } from "vue-router";

import type { RecentUpdate } from "../types";

defineProps<{ updates: RecentUpdate[] }>();
</script>

<template>
  <div class="grid gap-2 sm:grid-cols-2">
    <RouterLink
      v-for="u in updates"
      :key="u.series.id"
      :to="`/series/${u.series.id}`"
      class="flex items-center gap-3 rounded-box bg-base-100 p-2 transition hover:bg-base-300/40"
    >
      <img :src="u.series.coverUrl" :alt="u.series.title" class="cover h-16 shrink-0 rounded object-cover" />
      <div class="min-w-0 grow">
        <h4 class="truncate text-sm font-medium">{{ u.series.title }}</h4>
        <p class="text-xs text-base-content/60">{{ u.chapterLabel }} · {{ u.updatedAt }}</p>
      </div>
      <span v-if="u.series.unreadCount > 0" class="badge badge-primary badge-sm">
        {{ u.series.unreadCount }}
      </span>
    </RouterLink>
  </div>
</template>
