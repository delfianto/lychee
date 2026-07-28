<script setup lang="ts">
import { contentRatingClass } from "../lib/display";
import { demographicLabel, ratingLabel } from "../lib/ratingLabels";
import type { Series } from "../types";

defineProps<{ series: Series }>();

const cap = (s: string): string => s.charAt(0).toUpperCase() + s.slice(1);

const trackers = [
  { label: "AniList", href: "#" },
  { label: "MyAnimeList", href: "#" },
  { label: "MangaUpdates", href: "#" },
];
</script>

<template>
  <div class="card bg-base-100">
    <div class="card-body gap-4 p-4">
      <div class="flex flex-col gap-3 text-sm">
        <div>
          <div class="text-xs text-base-content/60">Author</div>
          <div>{{ series.authors.join(", ") }}</div>
        </div>
        <div>
          <div class="text-xs text-base-content/60">Artist</div>
          <div>{{ series.artists.join(", ") }}</div>
        </div>
        <div>
          <div class="text-xs text-base-content/60">Demographic</div>
          <span class="badge badge-sm badge-outline">{{ demographicLabel(series.demographic) }}</span>
        </div>
        <div>
          <div class="text-xs text-base-content/60">Content rating</div>
          <span class="badge badge-sm" :class="contentRatingClass[series.contentRating]">
            {{ ratingLabel(series.contentRating) }}
          </span>
        </div>
        <div>
          <div class="text-xs text-base-content/60">Publication</div>
          <div>{{ cap(series.status) }}<template v-if="series.year"> · {{ series.year }}</template></div>
        </div>
      </div>

      <div class="flex flex-col gap-2">
        <div class="text-xs text-base-content/60">Tags</div>
        <div class="flex flex-wrap gap-1">
          <span v-for="t in series.tags" :key="t.id" class="badge badge-outline badge-sm">{{ t.name }}</span>
        </div>
      </div>

      <div class="flex flex-col gap-2">
        <div class="text-xs text-base-content/60">Tracking</div>
        <div class="flex flex-wrap gap-1">
          <a v-for="tr in trackers" :key="tr.label" :href="tr.href" class="badge badge-sm badge-outline">
            {{ tr.label }}
          </a>
        </div>
      </div>
    </div>
  </div>
</template>
