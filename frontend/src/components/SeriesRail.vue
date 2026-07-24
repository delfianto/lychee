<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";
import { RouterLink } from "vue-router";

import type { Series } from "../types";

defineProps<{ series: Series[] }>();

const track = ref<HTMLElement | null>(null);
const page = ref(0);
const pageCount = ref(1);

function measure(): void {
  const el = track.value;
  if (!el) return;
  pageCount.value = Math.max(1, Math.ceil(el.scrollWidth / el.clientWidth));
  page.value = Math.round(el.scrollLeft / el.clientWidth);
}

function onScroll(): void {
  const el = track.value;
  if (el) page.value = Math.round(el.scrollLeft / el.clientWidth);
}

// Translate vertical wheel into horizontal scroll while hovering — but release
// to the page at the edges so you can still scroll past the carousel.
function onWheel(e: WheelEvent): void {
  const el = track.value;
  if (!el || el.scrollWidth <= el.clientWidth) return;
  const delta = e.deltaY + e.deltaX;
  const atStart = el.scrollLeft <= 0;
  const atEnd = el.scrollLeft + el.clientWidth >= el.scrollWidth - 1;
  if ((delta < 0 && atStart) || (delta > 0 && atEnd)) return;
  e.preventDefault();
  el.scrollLeft += delta;
}

function goto(i: number): void {
  const el = track.value;
  if (el) el.scrollTo({ left: i * el.clientWidth, behavior: "smooth" });
}

let ro: ResizeObserver | null = null;
onMounted(() => {
  measure();
  ro = new ResizeObserver(measure);
  if (track.value) ro.observe(track.value);
});
onBeforeUnmount(() => ro?.disconnect());
</script>

<template>
  <div class="flex flex-col gap-2">
    <div
      ref="track"
      class="no-scrollbar flex gap-4 overflow-x-auto"
      @scroll.passive="onScroll"
      @wheel="onWheel"
    >
      <RouterLink
        v-for="s in series"
        :key="s.id"
        :to="`/series/${s.id}`"
        class="group w-36 shrink-0 sm:w-44"
      >
        <img
          :src="s.coverUrl"
          :alt="s.title"
          class="cover w-full rounded-box object-cover transition group-hover:opacity-90"
        />
        <p class="mt-1.5 line-clamp-2 text-sm font-medium leading-tight">{{ s.title }}</p>
      </RouterLink>
    </div>

    <!-- Pagination dots -->
    <div v-if="pageCount > 1" class="flex justify-center gap-1.5 pt-1">
      <button
        v-for="i in pageCount"
        :key="i"
        class="h-2 rounded-full transition-all"
        :class="page === i - 1 ? 'w-4 bg-primary' : 'w-2 bg-base-content/30 hover:bg-base-content/50'"
        :aria-label="`Go to page ${i}`"
        @click="goto(i - 1)"
      ></button>
    </div>
  </div>
</template>
