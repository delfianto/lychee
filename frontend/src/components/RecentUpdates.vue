<script setup lang="ts">
import { RouterLink } from "vue-router";

import type { RecentUpdate } from "../types";

defineProps<{ updates: RecentUpdate[] }>();
</script>

<template>
  <div class="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
    <RouterLink
      v-for="(u, i) in updates"
      :key="i"
      :to="`/series/${u.series.id}`"
      class="flex items-center gap-3 rounded-box bg-base-100 p-2 transition hover:bg-base-300/40"
    >
      <img :src="u.series.coverUrl" :alt="u.series.title" class="cover h-20 shrink-0 rounded object-cover" />
      <div class="flex min-w-0 grow flex-col gap-0.5">
        <div class="flex items-start justify-between gap-2">
          <h4 class="line-clamp-1 text-sm font-medium">{{ u.series.title }}</h4>
          <span v-if="u.series.unreadCount > 0" class="badge badge-primary badge-xs shrink-0">
            {{ u.series.unreadCount }}
          </span>
        </div>
        <p class="truncate text-xs text-base-content/70">
          <template v-if="u.volume !== null">Vol. {{ u.volume }} · </template>Ch. {{ u.chapter }}
        </p>
        <p class="text-xs text-base-content/50">{{ u.updatedAt }}</p>
      </div>
    </RouterLink>
  </div>
</template>
