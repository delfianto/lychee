<script setup lang="ts">
import { RouterLink } from "vue-router";
import type { HomeSeries } from "../types";
import CoverImage from "./CoverImage.vue";
import ShelfRail from "./ShelfRail.vue";
defineProps<{ series: HomeSeries[]; reading?: boolean; details?: boolean }>();
</script>

<template>
  <ShelfRail :item-count="series.length">
    <div v-for="s in series" :key="s.id" class="group w-36 shrink-0 sm:w-44">
      <RouterLink
        :to="s.kind === 'gallery' ? `/gallery/${s.id}` : `/series/${s.id}`"
        :aria-label="s.title"
        class="block"
      >
        <CoverImage
          :src="s.coverUrl"
          :alt="s.title"
          class="cover w-full rounded-box transition group-hover:opacity-90"
        />
        <p class="mt-1.5 min-h-10 line-clamp-2 text-sm font-medium leading-tight">{{ s.title }}</p>
      </RouterLink>
      <template v-if="reading">
        <p v-if="s.resumeChapterLabel" class="mt-1 text-xs text-base-content/60">
          Ch. {{ s.resumeChapterLabel }}
        </p>
        <RouterLink
          :to="`/read/${s.resumeChapterId ?? s.id}`"
          class="btn btn-primary btn-sm mt-2 w-full"
          >Continue</RouterLink
        >
      </template>
      <p v-else-if="details" class="mt-1 text-xs text-base-content/60">
        <template v-if="s.pageCount">{{ s.pageCount }} pages · </template>
        <template v-if="s.chapterCount"
          >{{ s.chapterCount }} local chapter{{ s.chapterCount === 1 ? "" : "s" }}</template
        >
        <template v-else-if="s.kind === 'gallery'">{{ s.imageCount ?? 0 }} images</template>
        <template v-else>Not downloaded</template>
      </p>
      <RouterLink
        v-if="!reading && details && s.pageCount && s.chapterCount"
        :to="`/read/${s.id}`"
        class="btn btn-ghost btn-sm mt-2 w-full surface-border"
        >Read now</RouterLink
      >
    </div>
  </ShelfRail>
</template>
