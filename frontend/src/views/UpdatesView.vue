<script setup lang="ts">
import { LayoutList, List } from "lucide-vue-next";
import { type Component, onMounted, ref } from "vue";

import { fetchUpdates } from "../api/queries";
import ChapterFeed from "../components/ChapterFeed.vue";
import SegmentedToggle from "../components/SegmentedToggle.vue";
import type { RecentUpdate } from "../types";

type FeedView = "list" | "thumb";
const view = ref<FeedView>("thumb");
const viewOptions: { value: FeedView; icon: Component; label: string }[] = [
  { value: "list", icon: List, label: "List view" },
  { value: "thumb", icon: LayoutList, label: "Thumbnail list view" },
];

const entries = ref<RecentUpdate[]>([]);
onMounted(async () => {
  entries.value = await fetchUpdates(false);
});
</script>

<template>
  <div class="flex flex-col gap-4 p-4 sm:p-6">
    <div class="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 class="text-3xl font-bold">Recently updated</h1>
        <p class="text-sm text-base-content/60">{{ entries.length }} chapter updates</p>
      </div>
      <SegmentedToggle v-model="view" :options="viewOptions" aria-label="Update view" />
    </div>
    <ChapterFeed :entries="entries" :view="view" />
  </div>
</template>
