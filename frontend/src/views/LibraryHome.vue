<script setup lang="ts">
import { BookMarked, BookOpen, ChevronRight, HardDrive, Library, Settings } from "lucide-vue-next";
import { computed, onMounted, ref } from "vue";
import { RouterLink } from "vue-router";

import { fetchDashboard, fetchLibrarySummaries, type LibrarySummary } from "../api/queries";
import ErrorState from "../components/ErrorState.vue";
import FeaturedCarousel from "../components/FeaturedCarousel.vue";
import RecentUpdates from "../components/RecentUpdates.vue";
import SeriesRail from "../components/SeriesRail.vue";
import type { RecentUpdate, Series } from "../types";

defineOptions({ name: "LibraryHome" });

const loading = ref(true);
const failed = ref(false);
const totalSeries = ref(0);
const unreadTotal = ref(0);
const readingCount = ref(0);
const continueReading = ref<Series[]>([]);
const homeUpdates = ref<RecentUpdate[]>([]);
const recentlyAdded = ref<Series[]>([]);
// Storage per library — hide empty (0 GB) ones so the strip stays uncluttered.
const storageLibs = ref<LibrarySummary[]>([]);

const isEmpty = computed(() => !loading.value && !failed.value && totalSeries.value === 0);

async function load(): Promise<void> {
  loading.value = true;
  failed.value = false;
  try {
    const [dashboard, summaries] = await Promise.all([fetchDashboard(), fetchLibrarySummaries()]);
    totalSeries.value = dashboard.stats.series;
    unreadTotal.value = dashboard.stats.unreadChapters;
    readingCount.value = dashboard.stats.reading;
    continueReading.value = dashboard.continueReading;
    homeUpdates.value = dashboard.recentUpdates;
    recentlyAdded.value = dashboard.recentlyAdded;
    storageLibs.value = summaries.filter((l) => l.sizeGb > 0);
  } catch {
    failed.value = true;
  } finally {
    loading.value = false;
  }
}
onMounted(load);
</script>

<template>
  <div class="flex flex-col gap-8 p-4 sm:p-6">
    <!-- Skeleton while the dashboard loads -->
    <div v-if="loading" class="flex flex-col gap-8">
      <div class="flex flex-wrap gap-3">
        <div v-for="i in 3" :key="i" class="h-20 w-36 animate-pulse rounded-box bg-base-300" />
      </div>
      <div class="h-48 animate-pulse rounded-box bg-base-300" />
      <div class="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <div v-for="i in 6" :key="i" class="cover animate-pulse rounded-box bg-base-300" />
      </div>
    </div>
    <ErrorState v-else-if="failed" message="Couldn't load your dashboard." @retry="load" />

    <!-- Empty library onboarding -->
    <div
      v-else-if="isEmpty"
      class="flex flex-col items-center gap-4 rounded-box surface-border bg-base-100 px-6 py-16 text-center"
    >
      <Library class="size-12 text-primary/70" />
      <div class="max-w-md">
        <h1 class="text-2xl font-bold">Your library is empty</h1>
        <p class="mt-2 text-sm text-base-content/70">
          Add a local library folder, import archives, or connect MangaDex to sync your follows —
          then your shelves will fill in here.
        </p>
      </div>
      <div class="flex flex-wrap justify-center gap-2">
        <RouterLink to="/settings" class="btn btn-primary gap-1.5">
          <Settings class="size-4" />Open settings
        </RouterLink>
      </div>
    </div>

    <template v-else>
    <!-- At-a-glance stats -->
    <div class="stats stats-vertical w-full surface-border bg-base-100 shadow-sm sm:stats-horizontal sm:w-auto sm:self-start">
      <RouterLink to="/manga" class="stat transition hover:bg-base-200">
        <div class="stat-figure text-primary"><Library class="size-7" /></div>
        <div class="stat-title">Series</div>
        <div class="stat-value text-2xl">{{ totalSeries }}</div>
      </RouterLink>
      <RouterLink to="/unread" class="stat transition hover:bg-base-200">
        <div class="stat-figure text-primary"><BookOpen class="size-7" /></div>
        <div class="stat-title">Unread chapters</div>
        <div class="stat-value text-2xl">{{ unreadTotal }}</div>
      </RouterLink>
      <RouterLink to="/reading" class="stat transition hover:bg-base-200">
        <div class="stat-figure text-primary"><BookMarked class="size-7" /></div>
        <div class="stat-title">Reading</div>
        <div class="stat-value text-2xl">{{ readingCount }}</div>
      </RouterLink>
      <RouterLink
        v-for="lib in storageLibs"
        :key="lib.key"
        :to="`/${lib.key}`"
        class="stat transition hover:bg-base-200"
      >
        <div class="stat-figure text-primary"><HardDrive class="size-7" /></div>
        <div class="stat-title">{{ lib.title }}</div>
        <div class="stat-value text-2xl">
          {{ lib.sizeGb }}<span class="ml-1 text-base font-normal text-base-content/60">GB</span>
        </div>
      </RouterLink>
    </div>

    <!-- Continue reading — hidden when empty -->
    <section v-if="continueReading.length" class="flex flex-col gap-3">
      <h2 class="text-lg font-semibold">Continue reading</h2>
      <FeaturedCarousel :items="continueReading" />
    </section>

    <!-- Recent updates — hidden when empty -->
    <section v-if="homeUpdates.length" class="flex flex-col gap-3">
      <div class="flex items-center justify-between gap-2">
        <h2 class="text-lg font-semibold">Recent updates</h2>
        <RouterLink to="/updates" class="btn btn-circle btn-ghost btn-sm" aria-label="See all updates">
          <ChevronRight class="size-5" />
        </RouterLink>
      </div>
      <RecentUpdates :updates="homeUpdates" />
    </section>

    <!-- Recently added — hidden when empty -->
    <section v-if="recentlyAdded.length" class="flex flex-col gap-3">
      <div class="flex items-center justify-between gap-2">
        <h2 class="text-lg font-semibold">Recently added</h2>
        <RouterLink to="/added" class="btn btn-circle btn-ghost btn-sm" aria-label="See all recently added">
          <ChevronRight class="size-5" />
        </RouterLink>
      </div>
      <SeriesRail :series="recentlyAdded" />
    </section>
    </template>
  </div>
</template>
