<script setup lang="ts">
import { Bookmark, BookOpen, Check, Heart, ListPlus, RefreshCw, Star } from "lucide-vue-next";
import { computed, ref } from "vue";
import { RouterLink, useRoute } from "vue-router";

import ChapterList from "../components/ChapterList.vue";
import CountryFlag from "../components/CountryFlag.vue";
import SeriesInfoPanel from "../components/SeriesInfoPanel.vue";
import { contentRatingClass, contentRatingLabel, statusColor } from "../lib/display";
import { toast } from "../lib/toast";
import { findSeries, mockVolumes } from "../mocks/library";
import { useCollections } from "../stores/collections";
import type { Collection, LibraryStatus } from "../types";

const route = useRoute();
const series = computed(() => findSeries(String(route.params.id)));
const collections = useCollections();

function toggleList(l: Collection): void {
  const wasIn = collections.hasSeries(l.id, series.value.id);
  collections.toggleSeries(l.id, series.value.id);
  toast(wasIn ? `Removed from ${l.name}` : `Added to ${l.name}`, wasIn ? "info" : "success");
}

const expanded = ref(false);
const favorite = ref(true);
const rating = ref<number | null>(8.4);
const libraryStatus = ref<LibraryStatus>("reading");

const statuses: { value: LibraryStatus; label: string }[] = [
  { value: "none", label: "None" },
  { value: "reading", label: "Reading" },
  { value: "on_hold", label: "On Hold" },
  { value: "dropped", label: "Dropped" },
  { value: "plan_to_read", label: "Plan to Read" },
  { value: "completed", label: "Completed" },
  { value: "re_reading", label: "Re-Reading" },
];
const statusLabel = computed(
  () => statuses.find((s) => s.value === libraryStatus.value)?.label ?? "None",
);
const cap = (s: string): string => s.charAt(0).toUpperCase() + s.slice(1);
</script>

<template>
  <div class="flex flex-col gap-6">
    <!-- HERO -->
    <section class="relative overflow-hidden">
      <img
        :src="series.coverUrl"
        alt=""
        aria-hidden="true"
        class="absolute inset-0 h-full w-full object-cover opacity-30 blur-3xl"
      />
      <div class="absolute inset-0 bg-base-200/70"></div>

      <div class="relative flex flex-col gap-4 p-4 sm:flex-row sm:gap-6 sm:p-6">
        <img
          :src="series.coverUrl"
          :alt="series.title"
          class="cover w-36 shrink-0 rounded-box object-cover shadow-lg sm:w-48"
        />
        <div class="flex min-w-0 grow flex-col gap-3">
          <div class="flex flex-col gap-1">
            <h1 class="flex items-center gap-2 text-3xl font-bold">
              <CountryFlag v-if="series.originCountry" :cc="series.originCountry" />
              {{ series.title }}
            </h1>
            <p class="text-sm text-base-content/70">{{ series.authors.join(", ") }}</p>
            <div class="flex flex-wrap items-center gap-2 text-xs">
              <span class="flex items-center gap-1.5">
                <span class="size-2 rounded-full" :class="statusColor[series.status]"></span>
                {{ cap(series.status) }}
              </span>
              <span v-if="series.year" class="text-base-content/60">· {{ series.year }}</span>
              <span class="badge badge-sm" :class="contentRatingClass[series.contentRating]">
                {{ contentRatingLabel[series.contentRating] }}
              </span>
            </div>
          </div>

          <!-- Synopsis -->
          <div>
            <p class="text-sm text-base-content/80" :class="{ 'line-clamp-3': !expanded }">
              {{ series.description }}
            </p>
            <button class="btn btn-ghost btn-xs mt-1" @click="expanded = !expanded">
              {{ expanded ? "Show less" : "Show more" }}
            </button>
          </div>

          <!-- Action row: local controls (left) · upstream actions (right) -->
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div class="flex flex-wrap items-center gap-2">
              <RouterLink :to="`/read/${series.id}`" class="btn btn-primary btn-sm gap-2">
                <BookOpen class="size-4" />
                Start reading
              </RouterLink>

              <!-- Library status -->
              <div class="dropdown">
                <div tabindex="0" role="button" class="btn btn-sm gap-2">
                  <Bookmark class="size-4" />{{ statusLabel }}
                </div>
                <ul
                  tabindex="0"
                  class="menu dropdown-content z-10 mt-1 w-44 rounded-box bg-base-100 p-2 shadow"
                >
                  <li v-for="s in statuses" :key="s.value">
                    <a :class="{ 'menu-active': s.value === libraryStatus }" @click="libraryStatus = s.value">
                      {{ s.label }}
                    </a>
                  </li>
                </ul>
              </div>

              <!-- Rating · Favorite -->
              <div class="join">
                <button class="btn btn-sm join-item gap-1">
                  <Star class="size-4" /><span v-if="rating !== null">{{ rating }}</span>
                </button>
                <button
                  class="btn btn-square btn-sm join-item"
                  :class="{ 'text-error': favorite }"
                  aria-label="Favorite"
                  @click="favorite = !favorite"
                >
                  <Heart class="size-4" :class="{ 'fill-current': favorite }" />
                </button>
              </div>

              <!-- Add to list -->
              <div class="dropdown">
                <div tabindex="0" role="button" class="btn btn-square btn-sm" aria-label="Add to list">
                  <ListPlus class="size-4" />
                </div>
                <ul tabindex="0" class="menu dropdown-content z-10 mt-1 w-56 rounded-box bg-base-100 p-2 shadow">
                  <li class="menu-title">Add to list</li>
                  <li v-for="l in collections.lists" :key="l.id">
                    <a @click="toggleList(l)">
                      <Check
                        class="size-4"
                        :class="collections.hasSeries(l.id, series.id) ? 'opacity-100' : 'opacity-0'"
                      />
                      {{ l.name }}
                    </a>
                  </li>
                  <li v-if="!collections.lists.length" class="px-2 py-1 text-xs text-base-content/50">
                    No lists yet
                  </li>
                </ul>
              </div>
            </div>

            <div class="join">
              <button class="btn btn-sm join-item">Track</button>
              <button
                class="btn btn-square btn-sm join-item tooltip tooltip-bottom"
                data-tip="Check MangaDex for updates"
                aria-label="Check MangaDex for updates"
              >
                <RefreshCw class="size-4" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- BODY: info column (left) · chapters (right) -->
    <div class="flex flex-col gap-6 px-4 pb-6 sm:px-6 lg:flex-row">
      <aside class="shrink-0 lg:w-72">
        <SeriesInfoPanel :series="series" />
      </aside>
      <div class="min-w-0 grow">
        <ChapterList :volumes="mockVolumes" />
      </div>
    </div>
  </div>
</template>
