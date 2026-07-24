<script setup lang="ts">
import { ChevronDown, MessageSquare } from "lucide-vue-next";
import { RouterLink } from "vue-router";

import type { VolumeGroup } from "../types";

defineProps<{ volumes: VolumeGroup[] }>();
</script>

<template>
  <div class="flex flex-col gap-3">
    <!-- Tabs -->
    <div role="tablist" class="tabs tabs-border">
      <a role="tab" class="tab tab-active">Chapters</a>
      <a role="tab" class="tab">Related</a>
      <a role="tab" class="tab">Art</a>
    </div>

    <!-- Toolbar -->
    <div class="flex items-center gap-2">
      <select class="select select-bordered select-sm w-40">
        <option>English</option>
        <option>All languages</option>
      </select>
      <button class="btn btn-ghost btn-sm ml-auto gap-1">Newest<ChevronDown class="size-4" /></button>
    </div>

    <!-- Volume groups -->
    <div v-for="vg in volumes" :key="vg.volume ?? 'none'" class="flex flex-col gap-1">
      <div class="text-sm font-semibold text-base-content/70">
        {{ vg.volume === null ? "No volume" : `Volume ${vg.volume}` }}
      </div>
      <div class="overflow-hidden rounded-box border border-base-300">
        <RouterLink
          v-for="c in vg.chapters"
          :key="c.id"
          :to="`/read/${c.id}`"
          class="flex items-center gap-3 border-b border-base-300 px-3 py-2 last:border-b-0 hover:bg-base-300/40"
          :class="{ 'opacity-50': c.read }"
        >
          <span class="h-2 w-2 shrink-0 rounded-full" :class="c.read ? 'bg-base-300' : 'bg-primary'"></span>
          <span class="w-16 shrink-0 text-sm font-medium">Ch. {{ c.number }}</span>
          <span class="min-w-0 grow truncate text-sm">{{ c.title }}</span>
          <span class="hidden text-xs text-base-content/60 sm:inline">{{ c.group }}</span>
          <span class="badge badge-ghost badge-sm uppercase">{{ c.language }}</span>
          <span class="hidden w-16 shrink-0 text-right text-xs text-base-content/60 sm:inline">{{ c.uploadedAt }}</span>
          <span class="hidden w-12 shrink-0 items-center justify-end gap-1 text-xs text-base-content/50 md:inline-flex">
            <MessageSquare class="size-3.5" />{{ c.comments }}
          </span>
        </RouterLink>
      </div>
    </div>
  </div>
</template>
