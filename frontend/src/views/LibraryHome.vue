<script setup lang="ts">
import { BookMarked, BookOpen, ChevronRight, Library } from "lucide-vue-next";
import { RouterLink } from "vue-router";

import FeaturedCarousel from "../components/FeaturedCarousel.vue";
import RecentUpdates from "../components/RecentUpdates.vue";
import SeriesRail from "../components/SeriesRail.vue";
import { continueReading, librarySeries, recentlyAdded, recentUpdates } from "../mocks/library";

const totalSeries = librarySeries.length;
const unreadTotal = librarySeries.reduce((sum, s) => sum + s.unreadCount, 0);
const readingCount = librarySeries.filter((s) => s.lastReadChapter !== undefined).length;
const homeUpdates = recentUpdates.slice(0, 12);
</script>

<template>
  <div class="flex flex-col gap-8 p-4 sm:p-6">
    <!-- At-a-glance stats -->
    <div class="stats stats-vertical w-full bg-base-100 shadow-sm sm:stats-horizontal sm:w-auto sm:self-start">
      <div class="stat">
        <div class="stat-figure text-primary"><Library class="size-7" /></div>
        <div class="stat-title">Series</div>
        <div class="stat-value text-2xl">{{ totalSeries }}</div>
      </div>
      <div class="stat">
        <div class="stat-figure text-primary"><BookOpen class="size-7" /></div>
        <div class="stat-title">Unread chapters</div>
        <div class="stat-value text-2xl">{{ unreadTotal }}</div>
      </div>
      <div class="stat">
        <div class="stat-figure text-primary"><BookMarked class="size-7" /></div>
        <div class="stat-title">Reading</div>
        <div class="stat-value text-2xl">{{ readingCount }}</div>
      </div>
    </div>

    <!-- Continue reading -->
    <section class="flex flex-col gap-3">
      <h2 class="text-lg font-semibold">Continue reading</h2>
      <FeaturedCarousel :items="continueReading" />
    </section>

    <!-- Recent updates -->
    <section class="flex flex-col gap-3">
      <div class="flex items-center justify-between gap-2">
        <h2 class="text-lg font-semibold">Recent updates</h2>
        <RouterLink to="/updates" class="btn btn-circle btn-ghost btn-sm" aria-label="See all updates">
          <ChevronRight class="size-5" />
        </RouterLink>
      </div>
      <RecentUpdates :updates="homeUpdates" />
    </section>

    <!-- Recently added -->
    <section class="flex flex-col gap-3">
      <div class="flex items-center justify-between gap-2">
        <h2 class="text-lg font-semibold">Recently added</h2>
        <RouterLink to="/added" class="btn btn-circle btn-ghost btn-sm" aria-label="See all recently added">
          <ChevronRight class="size-5" />
        </RouterLink>
      </div>
      <SeriesRail :series="recentlyAdded" />
    </section>
  </div>
</template>
