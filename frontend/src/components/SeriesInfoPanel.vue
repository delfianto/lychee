<script setup lang="ts">
import CreatorCredits from "./CreatorCredits.vue";
import { ExternalLink } from "@lucide/vue";
import { RouterLink } from "vue-router";
import { contentRatingClass } from "../lib/display";
import { metadataBrowseLink } from "../lib/metadataBrowse";
import { demographicLabel, ratingLabel } from "../lib/ratingLabels";
import type { Series } from "../types";

defineProps<{ series: Series }>();

const cap = (s: string): string => s.charAt(0).toUpperCase() + s.slice(1);
</script>

<template>
  <div class="card bg-base-100">
    <div class="card-body gap-4 p-4">
      <div class="flex flex-col gap-3 text-sm">
        <div>
          <div class="text-xs text-base-content/60">Author</div>
          <CreatorCredits :names="series.authors" role="author" />
        </div>
        <div>
          <div class="text-xs text-base-content/60">Artist</div>
          <CreatorCredits :names="series.artists" role="artist" />
        </div>
        <div>
          <div class="text-xs text-base-content/60">Demographic</div>
          <RouterLink
            :to="metadataBrowseLink(series, 'demographics', series.demographic)"
            class="badge badge-sm badge-outline link link-hover"
            >{{ demographicLabel(series.demographic) }}</RouterLink
          >
        </div>
        <div>
          <div class="text-xs text-base-content/60">Content rating</div>
          <RouterLink
            :to="metadataBrowseLink(series, 'ratings', series.contentRating)"
            class="badge badge-sm link link-hover"
            :class="contentRatingClass[series.contentRating]"
          >
            {{ ratingLabel(series.contentRating) }}
          </RouterLink>
        </div>
        <div>
          <div class="text-xs text-base-content/60">Publication</div>
          <div>
            <RouterLink
              :to="metadataBrowseLink(series, 'pubStatus', series.status)"
              class="link link-hover"
              >{{ cap(series.status) }}</RouterLink
            ><template v-if="series.year"> · {{ series.year }}</template>
          </div>
        </div>
      </div>

      <div class="flex flex-col gap-2">
        <div class="text-xs text-base-content/60">Tags</div>
        <div class="flex flex-wrap gap-1">
          <RouterLink
            v-for="t in series.tags"
            :key="t.id"
            :to="metadataBrowseLink(series, 'tags', t.id)"
            class="badge badge-outline badge-sm link link-hover"
            >{{ t.name }}</RouterLink
          >
        </div>
      </div>

      <div v-if="series.sourceUrl" class="flex flex-col gap-2">
        <div class="text-xs text-base-content/60">Source</div>
        <a
          :href="series.sourceUrl"
          target="_blank"
          rel="noopener noreferrer"
          class="link link-hover inline-flex items-center gap-1 text-sm"
          ><ExternalLink class="size-4" />Open on MangaDex</a
        >
      </div>
    </div>
  </div>
</template>
