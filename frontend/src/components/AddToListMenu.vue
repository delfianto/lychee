<script setup lang="ts">
// Reusable "Add to list" dropdown — toggles a series' membership in each collection.
// Used on series/gallery detail and on grid cards. Clicks stop propagation so it works
// inside a card's RouterLink without navigating.
import { Check, ListPlus } from "lucide-vue-next";

import { toast } from "../lib/toast";
import { useCollections } from "../stores/collections";
import type { Collection } from "../types";

const props = withDefaults(
  defineProps<{ seriesId: string; triggerClass?: string }>(),
  { triggerClass: "btn btn-square btn-sm" },
);
const collections = useCollections();

function toggleList(list: Collection): void {
  const wasIn = collections.hasSeries(list.id, props.seriesId);
  collections.toggleSeries(list.id, props.seriesId);
  toast(wasIn ? `Removed from ${list.name}` : `Added to ${list.name}`, wasIn ? "info" : "success");
}
</script>

<template>
  <div class="dropdown dropdown-end">
    <div tabindex="0" role="button" :class="triggerClass" aria-label="Add to list" @click.stop>
      <ListPlus class="size-4" />
    </div>
    <ul tabindex="0" class="menu dropdown-content z-10 mt-1 w-56 rounded-box bg-base-100 p-2 shadow">
      <li class="menu-title">Add to list</li>
      <li v-for="l in collections.lists" :key="l.id">
        <a @click.stop.prevent="toggleList(l)">
          <Check class="size-4" :class="collections.hasSeries(l.id, seriesId) ? 'opacity-100' : 'opacity-0'" />
          {{ l.name }}
        </a>
      </li>
      <li v-if="!collections.lists.length" class="px-2 py-1 text-xs text-base-content/50">No lists yet</li>
    </ul>
  </div>
</template>
