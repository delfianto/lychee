<script setup lang="ts">
import { ChevronLeft, ChevronRight, Settings, X } from "lucide-vue-next";
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import SegmentedToggle from "../components/SegmentedToggle.vue";
import {
  type ReaderBackground,
  type ReaderDirection,
  type ReaderFit,
  type ReaderMode,
  useReaderSettings,
} from "../lib/readerSettings";
import { findSeries } from "../mocks/library";

const route = useRoute();
const router = useRouter();
const settings = useReaderSettings();

// Mock chapter pages (seeded by the route id so chapters differ).
const pages = Array.from(
  { length: 20 },
  (_, i) => `https://picsum.photos/seed/pg-${String(route.params.id)}-${i + 1}/800/1200`,
);
const series = findSeries(String(route.params.id));

const currentPage = ref(1);
const controls = ref(true);
const settingsOpen = ref(false);
const showEnd = ref(false);

const modes: { value: ReaderMode; label: string }[] = [
  { value: "single", label: "Single" },
  { value: "double", label: "Double" },
  { value: "longstrip", label: "Long strip" },
];
const directions: { value: ReaderDirection; label: string }[] = [
  { value: "ltr", label: "L → R" },
  { value: "rtl", label: "R → L" },
];
const fits: { value: ReaderFit; label: string }[] = [
  { value: "width", label: "Width" },
  { value: "height", label: "Height" },
  { value: "both", label: "Both" },
  { value: "original", label: "Original" },
];
const backgrounds: { value: ReaderBackground; label: string }[] = [
  { value: "dark", label: "Dark" },
  { value: "black", label: "Black" },
  { value: "sepia", label: "Sepia" },
];

const bgClass = computed(() =>
  settings.background === "black"
    ? "bg-black"
    : settings.background === "sepia"
      ? "reader-sepia"
      : "bg-base-300",
);

const fitClass = computed(() => {
  switch (settings.fit) {
    case "width":
      return "w-full h-auto";
    case "height":
      return "h-full w-auto";
    case "both":
      return "max-h-full max-w-full object-contain";
    default:
      return "max-w-none"; // original size
  }
});

function next(): void {
  if (currentPage.value >= pages.length) {
    showEnd.value = true;
    return;
  }
  currentPage.value += 1;
}
function prev(): void {
  showEnd.value = false;
  if (currentPage.value > 1) currentPage.value -= 1;
}
function nextChapter(): void {
  showEnd.value = false;
  currentPage.value = 1;
}

// Keyboard: ←/→ turn pages (direction-aware), Esc closes settings or exits.
function onKey(e: KeyboardEvent): void {
  if (e.key === "Escape") {
    if (settingsOpen.value) settingsOpen.value = false;
    else router.back();
    return;
  }
  if (settings.mode === "longstrip") return;
  if (e.key === "ArrowLeft") {
    e.preventDefault();
    if (settings.direction === "rtl") next();
    else prev();
  } else if (e.key === "ArrowRight") {
    e.preventDefault();
    if (settings.direction === "rtl") prev();
    else next();
  }
}
onMounted(() => window.addEventListener("keydown", onKey));
onBeforeUnmount(() => window.removeEventListener("keydown", onKey));
</script>

<template>
  <div class="relative h-dvh w-full overflow-hidden" :class="bgClass">
    <!-- Reading area -->
    <div v-if="settings.mode === 'longstrip'" class="h-full overflow-y-auto" @click="controls = !controls">
      <div class="mx-auto flex max-w-3xl flex-col items-center">
        <img v-for="(p, i) in pages" :key="i" :src="p" :alt="`Page ${i + 1}`" class="w-full" />
      </div>
    </div>
    <div v-else class="flex h-full items-center justify-center overflow-auto" @click="controls = !controls">
      <div class="flex items-center gap-1">
        <img :src="pages[currentPage - 1]" :alt="`Page ${currentPage}`" class="mx-auto" :class="fitClass" />
        <img
          v-if="settings.mode === 'double' && currentPage < pages.length"
          :src="pages[currentPage]"
          :alt="`Page ${currentPage + 1}`"
          :class="fitClass"
        />
      </div>
    </div>

    <!-- Page-turn click zones (paged modes) -->
    <template v-if="settings.mode !== 'longstrip'">
      <button
        class="absolute inset-y-0 left-0 w-1/4 cursor-pointer"
        aria-label="Previous page"
        @click.stop="settings.direction === 'rtl' ? next() : prev()"
      ></button>
      <button
        class="absolute inset-y-0 right-0 w-1/4 cursor-pointer"
        aria-label="Next page"
        @click.stop="settings.direction === 'rtl' ? prev() : next()"
      ></button>
    </template>

    <!-- Top overlay bar -->
    <header
      v-show="controls"
      class="navbar absolute inset-x-0 top-0 min-h-0 bg-base-100/80 py-1 backdrop-blur"
    >
      <div class="navbar-start gap-2">
        <button class="btn btn-circle btn-ghost btn-sm" aria-label="Back" @click="router.back()">
          <ChevronLeft class="size-5" />
        </button>
        <div class="flex flex-col leading-tight">
          <span class="text-sm font-medium">{{ series.title }}</span>
          <span class="text-xs text-base-content/60">Ch. 45 · Chapter title</span>
        </div>
      </div>
      <div class="navbar-end gap-1">
        <select class="select select-sm w-36" aria-label="Chapter">
          <option>Ch. 45</option>
          <option>Ch. 46</option>
          <option>Ch. 47</option>
        </select>
        <button class="btn btn-circle btn-ghost btn-sm" aria-label="Settings" @click="settingsOpen = !settingsOpen">
          <Settings class="size-5" />
        </button>
      </div>
    </header>

    <!-- Bottom overlay bar (scrubber) — paged modes only -->
    <footer
      v-show="controls && settings.mode !== 'longstrip'"
      class="absolute inset-x-0 bottom-0 flex items-center gap-3 bg-base-100/80 px-4 py-2 backdrop-blur"
    >
      <button class="btn btn-ghost btn-sm gap-1" @click="prev"><ChevronLeft class="size-4" />Prev</button>
      <input
        v-model.number="currentPage"
        type="range"
        min="1"
        :max="pages.length"
        class="range range-primary range-sm grow"
        aria-label="Page"
      />
      <span class="w-14 shrink-0 text-center text-xs">{{ currentPage }} / {{ pages.length }}</span>
      <button class="btn btn-ghost btn-sm gap-1" @click="next">Next<ChevronRight class="size-4" /></button>
    </footer>

    <!-- Settings panel -->
    <aside
      v-show="settingsOpen"
      class="absolute inset-y-0 right-0 z-20 flex w-72 flex-col gap-4 overflow-y-auto bg-base-100 p-4 shadow-xl"
    >
      <div class="flex items-center justify-between">
        <h3 class="font-semibold">Reader settings</h3>
        <button class="btn btn-circle btn-ghost btn-sm" aria-label="Close" @click="settingsOpen = false">
          <X class="size-5" />
        </button>
      </div>

      <div>
        <div class="mb-1 text-xs text-base-content/60">Reading mode</div>
        <SegmentedToggle v-model="settings.mode" :options="modes" aria-label="Reading mode" block />
      </div>

      <div>
        <div class="mb-1 text-xs text-base-content/60">Direction</div>
        <SegmentedToggle v-model="settings.direction" :options="directions" aria-label="Direction" block />
      </div>

      <div>
        <div class="mb-1 text-xs text-base-content/60">Fit</div>
        <SegmentedToggle v-model="settings.fit" :options="fits" aria-label="Fit" block />
      </div>

      <div>
        <div class="mb-1 text-xs text-base-content/60">Background</div>
        <SegmentedToggle v-model="settings.background" :options="backgrounds" aria-label="Background" block />
      </div>

      <p class="mt-auto text-xs text-base-content/50">Tip: ← / → turn pages, Esc exits.</p>
    </aside>

    <!-- End of chapter -->
    <div v-show="showEnd" class="absolute inset-0 z-30 flex items-center justify-center bg-base-300/90">
      <div class="card w-80 bg-base-100 shadow-xl">
        <div class="card-body items-center gap-3 text-center">
          <h3 class="card-title">End of chapter</h3>
          <p class="text-sm text-base-content/70">Next: Ch. 46</p>
          <div class="flex gap-2">
            <button class="btn btn-primary btn-sm" @click="nextChapter">Next chapter</button>
            <button class="btn btn-ghost btn-sm" @click="router.back()">Back to series</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
