<script setup lang="ts">
import FeaturedCarousel from "../components/FeaturedCarousel.vue";
import RecentUpdates from "../components/RecentUpdates.vue";
import SeriesGrid from "../components/SeriesGrid.vue";
import { continueReading, librarySeries, recentUpdates } from "../mocks/library";

const sorts = ["Title", "Recently added", "Recently read", "Unread"];
</script>

<template>
  <div class="flex flex-col gap-8 p-4 sm:p-6">
    <!-- Continue reading -->
    <section class="flex flex-col gap-3">
      <h2 class="text-lg font-semibold">Continue reading</h2>
      <FeaturedCarousel :items="continueReading" />
    </section>

    <!-- Recent updates -->
    <section class="flex flex-col gap-3">
      <h2 class="text-lg font-semibold">Recent updates</h2>
      <RecentUpdates :updates="recentUpdates" />
    </section>

    <!-- Library grid -->
    <section class="flex flex-col gap-3">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <h2 class="text-lg font-semibold">
          Manga <span class="text-sm font-normal text-base-content/60">· {{ librarySeries.length }} series</span>
        </h2>
        <select class="select select-bordered select-sm">
          <option v-for="s in sorts" :key="s">{{ s }}</option>
        </select>
      </div>
      <SeriesGrid :series="librarySeries" />
    </section>
  </div>
</template>
