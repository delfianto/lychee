<script setup lang="ts">
import { ChevronLeft, ChevronRight } from "@lucide/vue";
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";

const props = defineProps<{ itemCount: number; stacked?: boolean }>();

const track = ref<HTMLElement | null>(null);
const page = ref(0);
const pageCount = ref(1);

function measure(): void {
  const el = track.value;
  if (!el || !el.clientWidth) return;
  pageCount.value = Math.max(1, Math.ceil(el.scrollWidth / el.clientWidth));
  onScroll();
}

function onScroll(): void {
  const el = track.value;
  if (el && el.clientWidth)
    page.value =
      el.scrollLeft + el.clientWidth >= el.scrollWidth - 1
        ? pageCount.value - 1
        : Math.round(el.scrollLeft / el.clientWidth);
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
watch(
  () => props.itemCount,
  () => void nextTick(measure),
);
</script>

<template>
  <div class="flex min-w-0 flex-col gap-2">
    <div
      ref="track"
      class="no-scrollbar gap-4 overflow-x-auto"
      :class="stacked ? 'grid auto-cols-max grid-flow-col grid-rows-3' : 'flex'"
      @scroll.passive="onScroll"
      @wheel="onWheel"
    >
      <slot />
    </div>
    <!-- Pagination dots -->
    <div v-if="pageCount > 1" class="flex items-center justify-between gap-3 pt-1">
      <button
        class="btn btn-circle btn-ghost btn-sm"
        aria-label="Previous page"
        :disabled="page === 0"
        @click="goto(page - 1)"
      >
        <ChevronLeft class="size-4" />
      </button>
      <div v-if="pageCount <= 8" class="flex justify-center gap-1.5">
        <button
          v-for="i in pageCount"
          :key="i"
          class="h-2 rounded-full transition-all"
          :class="
            page === i - 1 ? 'w-4 bg-primary' : 'w-2 bg-base-content/30 hover:bg-base-content/50'
          "
          :aria-label="`Go to page ${i}`"
          @click="goto(i - 1)"
        ></button>
      </div>
      <span v-else class="text-xs text-base-content/50">{{ page + 1 }} / {{ pageCount }}</span>
      <button
        class="btn btn-circle btn-ghost btn-sm"
        aria-label="Next page"
        :disabled="page >= pageCount - 1"
        @click="goto(page + 1)"
      >
        <ChevronRight class="size-4" />
      </button>
    </div>
  </div>
</template>
