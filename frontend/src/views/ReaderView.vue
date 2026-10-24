<script setup lang="ts">
import { ChevronLeft, ChevronRight, Settings, X } from "@lucide/vue";
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from "vue-router";

import {
  bufferChapterPages,
  fetchChapterDetail,
  fetchChapters,
  fetchSeries,
  putProgress,
} from "../api/queries";
import SegmentedToggle from "../components/SegmentedToggle.vue";
import {
  clampPreloadPages,
  MAX_PRELOAD_PAGES,
  MIN_PRELOAD_PAGES,
  type ReaderBackground,
  type ReaderDirection,
  type ReaderFit,
  type ReaderMode,
  useReaderSettings,
} from "../lib/readerSettings";
import { createProgressWriter } from "../lib/readingProgress";
import { toast } from "../lib/toast";
import { createStaleGuard } from "../lib/staleGuard";

const route = useRoute();
const router = useRouter();
const settings = useReaderSettings();

const chapterId = computed(() => String(route.params.id));
const seriesId = ref("");
const seriesTitle = ref("");
const chapterLabel = ref("");
const pages = ref<string[]>([]);
const chapterOptions = ref<{ id: string; label: string }[]>([]);
const orderedIds = ref<string[]>([]);
const buffering = ref(false);
const loadedChapterId = ref("");
const loadedPages = new Set<number>();
const saveError = ref<string | null>(null);
const writer = createProgressWriter(putProgress, (error) => {
  saveError.value = error;
});
async function flushProgress(): Promise<void> {
  if (!(await writer.flush())) toast("Reading progress could not be saved.", "error");
}
onBeforeRouteLeave(flushProgress);
onBeforeRouteUpdate(flushProgress);
function onPageHide(): void {
  writer.finish();
}
function onVisibility(): void {
  if (document.visibilityState === "hidden") {
    writer.finish();
    void writer.flush();
  }
}

const currentPage = ref(1);
const controls = ref(true);
const settingsOpen = ref(false);
const showEnd = ref(false);
const readingArea = ref<HTMLElement | null>(null);

function readableId(
  c: { id: string | null; status?: string; providerChapterId?: string | null },
  sid: string,
): string | null {
  if (c.id && c.status === "downloaded") return c.id;
  if (c.providerChapterId) return `adhoc:${sid}:${c.providerChapterId}`;
  return c.id;
}

// Guards against a slower earlier chapter load (jumping chapter → chapter quickly,
// e.g. via the selector or next-chapter button) overwriting a newer one's state.
const staleGuard = createStaleGuard();
async function load(id: string): Promise<void> {
  const token = staleGuard.next();
  loadedChapterId.value = "";
  loadedPages.clear();
  pages.value = [];
  const isAdhoc = id.startsWith("adhoc:");
  buffering.value = isAdhoc;
  const preload = clampPreloadPages(settings.preloadPages);
  if (isAdhoc) {
    pages.value = [];
    await bufferChapterPages(id, 1, preload);
    if (!staleGuard.isCurrent(token)) return;
  }
  const detail = await fetchChapterDetail(id, isAdhoc ? preload : undefined);
  if (!staleGuard.isCurrent(token)) return;
  buffering.value = false;
  const resolvedId = detail.id;
  seriesId.value = detail.seriesId;
  chapterLabel.value = detail.title
    ? `Ch. ${detail.number} · ${detail.title}`
    : `Ch. ${detail.number}`;
  pages.value = Array.from(
    { length: detail.pageCount },
    (_, i) => `/api/chapters/${resolvedId}/pages/${i + 1}`,
  );
  currentPage.value = 1;
  loadedChapterId.value = resolvedId;
  showEnd.value = false;
  const [s, vols] = await Promise.all([
    fetchSeries(detail.seriesId),
    fetchChapters(detail.seriesId),
  ]);
  if (!staleGuard.isCurrent(token)) return;
  seriesTitle.value = s.title;
  const ascending = vols
    .flatMap((v) => v.chapters)
    .map((c) => ({ id: readableId(c, detail.seriesId), number: c.number }))
    .filter((c): c is { id: string; number: string } => !!c.id)
    .reverse(); // reading order
  orderedIds.value = ascending.map((c) => c.id);
  chapterOptions.value = ascending.map((c) => ({ id: c.id, label: `Ch. ${c.number}` }));
}
watch(chapterId, (id) => void load(id), { immediate: true });

const nextChapterId = computed(() => {
  const idx = orderedIds.value.indexOf(chapterId.value);
  return idx >= 0 ? orderedIds.value[idx + 1] : undefined;
});

function setPreloadPages(value: number): void {
  settings.preloadPages = clampPreloadPages(value);
}

// Save only pages whose images have loaded. Long-strip completion requires the
// bottom of the last image to be reached; a double spread includes both pages.
function recordPosition(): void {
  const id = loadedChapterId.value;
  if (!id || !pages.value.length) return;
  if (settings.mode === "longstrip") {
    onReadingScroll();
    return;
  }
  const last = Math.min(pages.value.length, currentPage.value + visibleColumns.value - 1);
  const visible = [...loadedPages].filter((page) => page >= currentPage.value && page <= last);
  if (!visible.length) return;
  const page = Math.max(...visible);
  writer.record(id, page, page === pages.value.length ? true : undefined);
}
function onImageLoad(event: Event): void {
  const page =
    pages.value.indexOf((event.target as HTMLImageElement).getAttribute("src") ?? "") + 1;
  if (page > 0) {
    loadedPages.add(page);
    recordPosition();
  }
}
function onReadingScroll(): void {
  if (settings.mode !== "longstrip" || !loadedChapterId.value) return;
  const area = readingArea.value;
  if (!area) return;
  const bounds = area.getBoundingClientRect();
  const images = [...area.querySelectorAll<HTMLImageElement>("img")];
  if (bounds.height <= 0) return;
  const last = images.at(-1);
  const reachedEnd =
    !!last &&
    loadedPages.size === images.length &&
    last.getBoundingClientRect().height > 0 &&
    last.getBoundingClientRect().bottom <= bounds.bottom + 2;
  const visible = images.findIndex(
    (image) => image.getBoundingClientRect().bottom > bounds.top + bounds.height / 2,
  );
  if (reachedEnd) {
    currentPage.value = images.length;
    writer.record(loadedChapterId.value, images.length, true);
  } else if (visible >= 0 && loadedPages.has(visible + 1)) {
    currentPage.value = visible + 1;
    writer.record(loadedChapterId.value, Math.min(visible + 1, images.length - 1));
  }
}
watch([currentPage, () => settings.mode, loadedChapterId], () => {
  recordPosition();
  if (loadedChapterId.value.startsWith("adhoc:"))
    void bufferChapterPages(
      loadedChapterId.value,
      currentPage.value,
      clampPreloadPages(settings.preloadPages),
    ).catch(() => {});
});
function goToChapter(id: string | undefined): void {
  if (id) void router.push(`/read/${id}`);
  else void router.push(seriesId.value ? `/series/${seriesId.value}` : "/");
}

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

const fitClass = computed(() => `reader-fit-${settings.fit}`);
const visibleColumns = computed(() =>
  settings.mode === "double" && currentPage.value < pages.value.length ? 2 : 1,
);

// Scrolling through a strip updates the page counter without resetting scroll.
async function resetViewport(): Promise<void> {
  await nextTick();
  if (readingArea.value) {
    readingArea.value.scrollTop = 0;
    readingArea.value.scrollLeft = 0;
  }
}
watch([loadedChapterId, () => settings.mode, () => settings.fit], resetViewport);
watch(currentPage, () => {
  if (settings.mode !== "longstrip") void resetViewport();
});

function onReadingClick(event: MouseEvent): void {
  if (settings.mode === "longstrip") {
    controls.value = !controls.value;
    return;
  }
  const bounds = readingArea.value?.getBoundingClientRect();
  const position = bounds?.width ? (event.clientX - bounds.left) / bounds.width : 0.5;
  // Handle navigation on the scroll surface; overlay buttons intercept wheel
  // and touch input before it can reach the image's scroll container.
  if (position < 0.25) {
    if (settings.direction === "rtl") next();
    else prev();
  } else if (position > 0.75) {
    if (settings.direction === "rtl") prev();
    else next();
  } else controls.value = !controls.value;
}

function next(): void {
  if (currentPage.value + visibleColumns.value - 1 >= pages.value.length) {
    showEnd.value = true;
    return;
  }
  currentPage.value = Math.min(pages.value.length, currentPage.value + visibleColumns.value);
}
function prev(): void {
  showEnd.value = false;
  if (currentPage.value > 1)
    currentPage.value = Math.max(1, currentPage.value - (settings.mode === "double" ? 2 : 1));
}
function nextChapter(): void {
  showEnd.value = false;
  goToChapter(nextChapterId.value);
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
onMounted(() => {
  window.addEventListener("keydown", onKey);
  window.addEventListener("pagehide", onPageHide);
  document.addEventListener("visibilitychange", onVisibility);
});
onBeforeUnmount(() => {
  window.removeEventListener("keydown", onKey);
  window.removeEventListener("pagehide", onPageHide);
  document.removeEventListener("visibilitychange", onVisibility);
  writer.finish();
});
</script>

<template>
  <div class="relative flex h-dvh w-full flex-col overflow-hidden" :class="bgClass">
    <!-- Controls occupy their own space, keeping page edges unobscured. -->
    <header
      v-show="controls"
      class="navbar relative z-10 min-h-0 shrink-0 bg-base-100/80 py-1 backdrop-blur"
    >
      <div class="navbar-start min-w-0 flex-1 gap-2">
        <button class="btn btn-circle btn-ghost btn-sm" aria-label="Back" @click="router.back()">
          <ChevronLeft class="size-5" />
        </button>
        <div class="flex min-w-0 flex-col leading-tight">
          <span class="truncate text-sm font-medium">{{ seriesTitle }}</span>
          <span class="truncate text-xs text-base-content/60">{{ chapterLabel }}</span>
        </div>
      </div>
      <div class="navbar-end w-auto shrink-0 gap-1">
        <select
          class="select select-sm w-28 sm:w-36"
          aria-label="Chapter"
          :value="chapterId"
          @change="goToChapter(($event.target as HTMLSelectElement).value)"
        >
          <option v-for="c in chapterOptions" :key="c.id" :value="c.id">{{ c.label }}</option>
        </select>
        <button
          class="btn btn-circle btn-ghost btn-sm"
          aria-label="Settings"
          @click="settingsOpen = !settingsOpen"
        >
          <Settings class="size-5" />
        </button>
      </div>
    </header>

    <!-- One viewport owns both axes of scrolling in every reading mode. -->
    <div
      v-if="!pages.length"
      class="flex min-h-0 flex-1 flex-col items-center justify-center gap-2"
    >
      <span class="loading loading-spinner loading-lg text-base-content/50" />
      <span v-if="buffering" class="text-xs text-base-content/60">
        Buffering {{ settings.preloadPages }} page(s)…
      </span>
    </div>
    <div
      v-else
      ref="readingArea"
      class="reader-viewport min-h-0 min-w-0 flex-1 overflow-auto overscroll-contain"
      role="region"
      aria-label="Reading area"
      tabindex="0"
      :style="{ '--reader-columns': visibleColumns }"
      @click="onReadingClick"
      @scroll.passive="onReadingScroll"
    >
      <div v-if="settings.mode === 'longstrip'" class="reader-strip">
        <img
          v-for="(p, i) in pages"
          :key="p"
          :src="p"
          :alt="`Page ${i + 1}`"
          class="reader-page"
          @load="onImageLoad"
          :class="fitClass"
        />
        <div class="flex justify-center gap-3 py-8">
          <button class="btn btn-primary btn-sm" @click.stop="goToChapter(nextChapterId)">
            {{ nextChapterId ? "Next chapter" : "Back to series" }}
          </button>
        </div>
      </div>
      <div v-else class="reader-spread">
        <img
          :src="pages[currentPage - 1]"
          :alt="`Page ${currentPage}`"
          class="reader-page"
          @load="onImageLoad"
          :class="fitClass"
        />
        <img
          v-if="visibleColumns === 2"
          :src="pages[currentPage]"
          :alt="`Page ${currentPage + 1}`"
          class="reader-page"
          @load="onImageLoad"
          :class="fitClass"
        />
      </div>
    </div>

    <div
      v-if="saveError"
      class="flex shrink-0 items-center justify-between gap-2 bg-error/10 px-4 py-2 text-sm"
      role="alert"
    >
      <span>{{ saveError }}</span
      ><button class="btn btn-ghost btn-xs" @click="writer.flush()">Retry save</button>
    </div>
    <!-- Scrubber — paged modes only. -->
    <footer
      v-if="settings.mode !== 'longstrip'"
      v-show="controls"
      class="relative z-10 flex shrink-0 items-center gap-3 bg-base-100/80 px-4 py-2 backdrop-blur"
    >
      <button class="btn btn-ghost btn-sm gap-1" aria-label="Previous page" @click="prev">
        <ChevronLeft class="size-4" />Prev
      </button>
      <input
        v-model.number="currentPage"
        type="range"
        min="1"
        :max="pages.length"
        class="range range-primary range-sm grow"
        aria-label="Page"
      />
      <span class="w-14 shrink-0 text-center text-xs">{{ currentPage }} / {{ pages.length }}</span>
      <button class="btn btn-ghost btn-sm gap-1" aria-label="Next page" @click="next">
        Next<ChevronRight class="size-4" />
      </button>
    </footer>

    <!-- Settings panel -->
    <aside
      v-show="settingsOpen"
      class="absolute inset-y-0 right-0 z-20 flex w-72 flex-col gap-4 overflow-y-auto bg-base-100 p-4 shadow-xl"
    >
      <div class="flex items-center justify-between">
        <h3 class="font-semibold">Reader settings</h3>
        <button
          class="btn btn-circle btn-ghost btn-sm"
          aria-label="Close"
          @click="settingsOpen = false"
        >
          <X class="size-5" />
        </button>
      </div>

      <div>
        <div class="mb-1 text-xs text-base-content/60">Reading mode</div>
        <SegmentedToggle v-model="settings.mode" :options="modes" aria-label="Reading mode" block />
      </div>

      <div>
        <div class="mb-1 text-xs text-base-content/60">Direction</div>
        <SegmentedToggle
          v-model="settings.direction"
          :options="directions"
          aria-label="Direction"
          block
        />
      </div>

      <div>
        <div class="mb-1 text-xs text-base-content/60">Fit</div>
        <SegmentedToggle v-model="settings.fit" :options="fits" aria-label="Fit" block />
      </div>

      <div>
        <div class="mb-1 text-xs text-base-content/60">Background</div>
        <SegmentedToggle
          v-model="settings.background"
          :options="backgrounds"
          aria-label="Background"
          block
        />
      </div>

      <div>
        <label class="mb-1 flex items-center justify-between text-xs text-base-content/60">
          <span>Ad-hoc preload pages</span>
          <span class="font-medium tabular-nums">{{ settings.preloadPages }}</span>
        </label>
        <input
          type="number"
          :min="MIN_PRELOAD_PAGES"
          :max="MAX_PRELOAD_PAGES"
          :value="settings.preloadPages"
          aria-label="Ad-hoc preload pages"
          class="input input-bordered input-sm w-full"
          @change="setPreloadPages(Number(($event.target as HTMLInputElement).value))"
        />
      </div>

      <p class="mt-auto text-xs text-base-content/50">Tip: ← / → turn pages, Esc exits.</p>
    </aside>

    <!-- End of chapter -->
    <div
      v-show="showEnd"
      class="absolute inset-0 z-30 flex items-center justify-center bg-base-300/90"
    >
      <div class="card w-80 bg-base-100 shadow-xl">
        <div class="card-body items-center gap-3 text-center">
          <h3 class="card-title">End of chapter</h3>
          <p class="text-sm text-base-content/70">
            {{ nextChapterId ? "Ready for the next chapter?" : "That was the last chapter." }}
          </p>
          <div class="flex gap-2">
            <button v-if="nextChapterId" class="btn btn-primary btn-sm" @click="nextChapter">
              Next chapter
            </button>
            <button class="btn btn-ghost btn-sm" @click="goToChapter(undefined)">
              Back to series
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
