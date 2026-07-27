<script setup lang="ts">
// Recently-updated and Unread-chapters are the same feed view, differing only
// in which chapters fetchUpdates() returns and a bit of copy.
import { LayoutList, List } from "lucide-vue-next";
import { type Component, onMounted, ref } from "vue";

import { fetchUpdates } from "../api/queries";
import ChapterFeed from "../components/ChapterFeed.vue";
import SegmentedToggle from "../components/SegmentedToggle.vue";
import type { RecentUpdate } from "../types";

const props = defineProps<{ unreadOnly: boolean }>();

type FeedView = "list" | "thumb";
const view = ref<FeedView>("thumb");
const viewOptions: { value: FeedView; icon: Component; label: string }[] = [
  { value: "list", icon: List, label: "List view" },
  { value: "thumb", icon: LayoutList, label: "Thumbnail list view" },
];

const entries = ref<RecentUpdate[]>([]);
const loading = ref(true);
onMounted(async () => {
  loading.value = true;
  entries.value = await fetchUpdates(props.unreadOnly);
  loading.value = false;
});
</script>

<template>
  <div class="flex flex-col gap-4 p-4 sm:p-6">
    <div class="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 class="text-3xl font-bold">{{ unreadOnly ? "Unread chapters" : "Recently updated" }}</h1>
        <p class="text-sm text-base-content/60">
          <template v-if="loading">Loading…</template>
          <template v-else>{{ entries.length }} {{ unreadOnly ? "unread chapters" : "chapter updates" }}</template>
        </p>
      </div>
      <SegmentedToggle v-model="view" :options="viewOptions" :aria-label="unreadOnly ? 'View' : 'Update view'" />
    </div>
    <div v-if="loading" class="flex justify-center py-16">
      <span class="loading loading-spinner loading-lg text-primary" />
    </div>
    <div v-else-if="!entries.length" class="py-16 text-center text-sm text-base-content/60">
      {{ unreadOnly ? "You're all caught up — no unread chapters." : "No chapter updates yet." }}
    </div>
    <!-- Every row is unread on the Unread page, so the per-row "new" badge would be noise there. -->
    <ChapterFeed v-else :entries="entries" :view="view" :new-badge="!unreadOnly" />
  </div>
</template>
