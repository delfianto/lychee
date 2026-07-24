<script setup lang="ts">
import { X } from "lucide-vue-next";
import { RouterLink } from "vue-router";

import type { Series } from "../types";
import CountryFlag from "./CountryFlag.vue";

defineProps<{ series: Series; removable?: boolean }>();
const emit = defineEmits<{ remove: [] }>();
</script>

<template>
  <RouterLink
    :to="series.kind === 'gallery' ? `/gallery/${series.id}` : `/series/${series.id}`"
    class="group relative block overflow-hidden rounded-box surface-border"
  >
    <img
      :src="series.coverUrl"
      :alt="series.title"
      class="cover w-full object-cover transition duration-300 group-hover:scale-105"
    />
    <button
      v-if="removable"
      class="btn btn-circle btn-error btn-xs absolute right-2 top-2"
      aria-label="Remove from list"
      @click.stop.prevent="emit('remove')"
    >
      <X class="size-3.5" />
    </button>
    <span
      v-else-if="series.unreadCount > 0"
      class="badge badge-primary badge-sm absolute right-2 top-2"
    >
      {{ series.unreadCount }}
    </span>
    <div class="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/85 via-black/40 to-transparent p-2 pt-8">
      <div class="flex items-start gap-1.5">
        <CountryFlag
          v-if="series.originCountry && series.kind !== 'gallery'"
          :cc="series.originCountry"
          class="mt-0.5 shadow"
        />
        <h3 class="line-clamp-2 text-sm font-semibold text-white">{{ series.title }}</h3>
      </div>
    </div>
  </RouterLink>
</template>
