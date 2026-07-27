<script setup lang="ts">
import { RouterLink } from "vue-router";

import type { RecentUpdate } from "../types";
import CountryFlag from "./CountryFlag.vue";
import CoverImage from "./CoverImage.vue";

// Chapter feed shared by the Recently-updated and Unread-chapters pages: a
// list of chapter rows with a compact "list" and a cover "thumb" density.
withDefaults(
  defineProps<{ entries: RecentUpdate[]; view: "list" | "thumb"; newBadge?: boolean }>(),
  { newBadge: true },
);
</script>

<template>
  <div class="flex flex-col gap-1.5">
    <RouterLink
      v-for="(u, i) in entries"
      :key="i"
      :to="`/read/${u.series.id}`"
      class="flex items-center gap-3 rounded-box surface-border bg-base-100 px-3 transition hover:bg-base-300/40"
      :class="view === 'thumb' ? 'py-2' : 'py-2.5'"
    >
      <CoverImage
        v-if="view === 'thumb'"
        :src="u.series.coverUrl"
        :alt="u.series.title"
        class="cover h-14 shrink-0 rounded"
      />
      <div class="flex min-w-0 grow items-center gap-2">
        <CountryFlag v-if="u.series.originCountry" :cc="u.series.originCountry" />
        <span class="truncate text-sm font-medium">{{ u.series.title }}</span>
        <span class="shrink-0 text-xs text-base-content/70">
          <template v-if="u.volume !== null">Vol. {{ u.volume }} · </template>Ch. {{ u.chapter }}
        </span>
        <span v-if="newBadge && u.series.unreadCount > 0" class="badge badge-primary badge-xs shrink-0">new</span>
      </div>
      <span class="shrink-0 text-xs text-base-content/50">{{ u.updatedAt }}</span>
    </RouterLink>
  </div>
</template>
