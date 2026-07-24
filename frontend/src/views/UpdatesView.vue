<script setup lang="ts">
import { LayoutList, List } from "lucide-vue-next";
import { type Component, ref } from "vue";
import { RouterLink } from "vue-router";

import CountryFlag from "../components/CountryFlag.vue";
import SegmentedToggle from "../components/SegmentedToggle.vue";
import { recentUpdates } from "../mocks/library";

type UpdatesView = "list" | "thumb";
const view = ref<UpdatesView>("thumb");
const viewOptions: { value: UpdatesView; icon: Component; label: string }[] = [
  { value: "list", icon: List, label: "List view" },
  { value: "thumb", icon: LayoutList, label: "Thumbnail list view" },
];
</script>

<template>
  <div class="flex flex-col gap-4 p-4 sm:p-6">
    <div class="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 class="text-3xl font-bold">Recently updated</h1>
        <p class="text-sm text-base-content/60">{{ recentUpdates.length }} chapter updates</p>
      </div>
      <SegmentedToggle v-model="view" :options="viewOptions" aria-label="Update view" />
    </div>

    <!-- Update feed -->
    <div class="flex flex-col gap-1.5">
      <RouterLink
        v-for="(u, i) in recentUpdates"
        :key="i"
        :to="`/read/${u.series.id}`"
        class="flex items-center gap-3 rounded-box surface-border bg-base-100 px-3 transition hover:bg-base-300/40"
        :class="view === 'thumb' ? 'py-2' : 'py-2.5'"
      >
        <img
          v-if="view === 'thumb'"
          :src="u.series.coverUrl"
          :alt="u.series.title"
          class="cover h-14 shrink-0 rounded object-cover"
        />
        <div class="flex min-w-0 grow items-center gap-2">
          <CountryFlag v-if="u.series.originCountry" :cc="u.series.originCountry" />
          <span class="truncate text-sm font-medium">{{ u.series.title }}</span>
          <span class="shrink-0 text-xs text-base-content/70">
            <template v-if="u.volume !== null">Vol. {{ u.volume }} · </template>Ch. {{ u.chapter }}
          </span>
          <span v-if="u.series.unreadCount > 0" class="badge badge-primary badge-xs shrink-0">new</span>
        </div>
        <span class="shrink-0 text-xs text-base-content/50">{{ u.updatedAt }}</span>
      </RouterLink>
    </div>
  </div>
</template>
