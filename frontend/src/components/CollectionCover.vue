<script setup lang="ts">
import { Layers } from "@lucide/vue";
import { computed } from "vue";
import CoverImage from "./CoverImage.vue";

const props = defineProps<{ seriesIds: string[] }>();
const covers = computed(() => props.seriesIds.slice(0, 4));
</script>

<template>
  <div
    class="grid aspect-video gap-0.5 overflow-hidden bg-base-300"
    :class="[
      covers.length > 1 ? 'grid-cols-2' : 'grid-cols-1',
      covers.length > 2 ? 'grid-rows-2' : 'grid-rows-1',
    ]"
  >
    <CoverImage
      v-for="(id, i) in covers"
      :key="id"
      :src="`/api/series/${id}/cover?v=2`"
      class="h-full min-h-0 w-full"
      :class="covers.length === 3 && i === 0 ? 'row-span-2' : ''"
    />
    <div v-if="!covers.length" class="flex h-full items-center justify-center text-base-content/30">
      <Layers class="size-8" />
    </div>
  </div>
</template>
