<script setup lang="ts">
import { Heart, Star } from "lucide-vue-next";
import { computed } from "vue";
import { RouterLink } from "vue-router";

import { contentRatingClass, contentRatingLabel, statusColor, statusLabel } from "../lib/display";
import type { Series } from "../types";
import AddToListMenu from "./AddToListMenu.vue";
import CountryFlag from "./CountryFlag.vue";

const props = defineProps<{ series: Series; compact?: boolean }>();

const maxTags = computed(() => (props.compact ? 3 : 6));
const shownTags = computed(() => props.series.tags.slice(0, maxTags.value));
const moreTags = computed(() => Math.max(0, props.series.tags.length - maxTags.value));
</script>

<template>
  <RouterLink
    :to="series.kind === 'gallery' ? `/gallery/${series.id}` : `/series/${series.id}`"
    class="group block"
  >
    <article class="flex gap-3 rounded-box surface-border bg-base-100 p-3 shadow-sm transition hover:shadow-md sm:gap-4">
      <img
        :src="series.coverUrl"
        :alt="series.title"
        class="cover shrink-0 rounded-box object-cover"
        :class="compact ? 'w-28' : 'w-20 sm:w-24'"
      />

      <div class="flex min-w-0 grow flex-col gap-1.5">
        <!-- Title row: flag + title · rating / favorite / status dot -->
        <div class="flex items-start justify-between gap-2">
          <h3
            class="flex min-w-0 items-center gap-1.5 font-semibold leading-tight"
            :class="compact ? 'text-sm' : 'text-base'"
          >
            <CountryFlag v-if="series.originCountry && series.kind !== 'gallery'" :cc="series.originCountry" />
            <span class="truncate group-hover:text-primary">{{ series.title }}</span>
          </h3>
          <div class="flex shrink-0 items-center gap-2">
            <span v-if="series.rating" class="flex items-center gap-0.5 text-xs font-medium">
              <Star class="size-3.5 fill-current text-warning" />{{ series.rating.toFixed(1) }}
            </span>
            <Heart
              class="size-4"
              :class="series.favorite ? 'fill-current text-error' : 'text-base-content/40'"
            />
            <span
              v-if="series.kind !== 'gallery'"
              class="size-2.5 shrink-0 rounded-full"
              :class="statusColor[series.status]"
              :title="statusLabel[series.status]"
            ></span>
            <div class="opacity-0 transition group-hover:opacity-100 focus-within:opacity-100">
              <AddToListMenu :series-id="series.id" trigger-class="btn btn-ghost btn-xs btn-square" />
            </div>
          </div>
        </div>

        <!-- Content rating + genre tags -->
        <div class="flex flex-wrap items-center gap-1">
          <span class="badge badge-sm" :class="contentRatingClass[series.contentRating]">
            {{ contentRatingLabel[series.contentRating] }}
          </span>
          <span v-for="tg in shownTags" :key="tg.id" class="badge badge-outline badge-sm">
            {{ tg.name }}
          </span>
          <span v-if="moreTags > 0" class="badge badge-ghost badge-sm">+{{ moreTags }}</span>
        </div>

        <!-- Synopsis -->
        <p
          class="text-xs text-base-content/60"
          :class="compact ? 'line-clamp-2' : 'line-clamp-2 sm:line-clamp-3'"
        >
          {{ series.description }}
        </p>

        <!-- Meta footer -->
        <div class="mt-auto flex items-center gap-2 pt-0.5 text-xs text-base-content/60">
          <span v-if="series.kind === 'gallery'">{{ series.imageCount }} images</span>
          <template v-else>
            <span>{{ series.chapterCount }} chapters</span>
            <span v-if="series.unreadCount > 0" class="badge badge-primary badge-sm">
              {{ series.unreadCount }} unread
            </span>
          </template>
        </div>
      </div>
    </article>
  </RouterLink>
</template>
