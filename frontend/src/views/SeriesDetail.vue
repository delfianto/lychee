<script setup lang="ts">
import { BookMarked, BookOpen, Heart, Link2, Pencil, RefreshCw, Star, X } from "lucide-vue-next";
import { computed, onUnmounted, ref, watch } from "vue";
import { RouterLink, useRoute } from "vue-router";

import { onTaskDone } from "../api/events";
import {
  fetchArt,
  fetchChapters,
  fetchRelated,
  fetchSeries,
  patchSeries,
  deleteChapterLocal,
  queueDownload,
  refreshSeries,
  unlinkMatch,
} from "../api/queries";
import AddToListMenu from "../components/AddToListMenu.vue";
import ChapterList from "../components/ChapterList.vue";
import CountryFlag from "../components/CountryFlag.vue";
import CoverImage from "../components/CoverImage.vue";
import EditSeriesModal from "../components/EditSeriesModal.vue";
import ErrorState from "../components/ErrorState.vue";
import MatchSeriesModal from "../components/MatchSeriesModal.vue";
import SeriesDescription from "../components/SeriesDescription.vue";
import SeriesInfoPanel from "../components/SeriesInfoPanel.vue";
import { contentRatingClass, contentRatingLabel, statusColor } from "../lib/display";
import { createStaleGuard } from "../lib/staleGuard";
import { toast } from "../lib/toast";
import type { LibraryStatus, Series, VolumeGroup } from "../types";

const route = useRoute();

const series = ref<Series | null>(null);
const volumes = ref<VolumeGroup[]>([]);
const related = ref<Series[]>([]);
const artCovers = ref<string[]>([]);
const loading = ref(true);
const chapterLanguage = ref("");
const chapterOrder = ref<"asc" | "desc">("desc");

const expanded = ref(false);
const favorite = ref(false);
const libraryStatus = ref<LibraryStatus>("none");
// Your personal rating (1–10, integer). The community score is series.rating (decimal).
const userRating = ref<number | null>(null);
const hoverRating = ref(0);

const failed = ref(false);
// Guards both loaders below against out-of-order responses (e.g. navigating series
// A → B before A's slower request resolves, or changing the chapter language/order
// again before the previous change's request lands) — whichever started last wins.
const staleGuard = createStaleGuard();
async function load(id: string, opts: { soft?: boolean } = {}): Promise<void> {
  const token = staleGuard.next();
  // Soft reload keeps existing content visible (same series refresh / download done).
  if (!opts.soft) {
    series.value = null;
    loading.value = true;
  }
  failed.value = false;
  try {
    const [s, vols, rel, art] = await Promise.all([
      fetchSeries(id),
      fetchChapters(id, { language: chapterLanguage.value, order: chapterOrder.value }),
      fetchRelated(id),
      fetchArt(id),
    ]);
    if (!staleGuard.isCurrent(token)) return;
    series.value = s;
    volumes.value = vols;
    related.value = rel;
    artCovers.value = art;
    favorite.value = s.favorite ?? false;
    libraryStatus.value = s.libraryStatus ?? "none";
    userRating.value = s.userRating ?? null;
  } catch {
    if (staleGuard.isCurrent(token)) failed.value = true;
  } finally {
    if (staleGuard.isCurrent(token)) loading.value = false;
  }
}
const reload = (): void => void load(String(route.params.id));

async function reloadChapters(): Promise<void> {
  const token = staleGuard.next();
  const vols = await fetchChapters(String(route.params.id), {
    language: chapterLanguage.value,
    order: chapterOrder.value,
  });
  if (staleGuard.isCurrent(token)) volumes.value = vols;
}
function onLanguageChange(language: string): void {
  chapterLanguage.value = language;
  void reloadChapters();
}
function onOrderChange(order: "asc" | "desc"): void {
  chapterOrder.value = order;
  void reloadChapters();
}
watch(
  () => route.params.id,
  (id, prev) => void load(String(id), { soft: prev !== undefined && String(id) === String(prev) }),
  { immediate: true },
);

async function downloadChapter(providerChapterId: string, done?: () => void): Promise<void> {
  if (!series.value) {
    done?.();
    return;
  }
  try {
    await queueDownload(series.value.id, [providerChapterId]);
    toast("Chapter queued");
    // Optimistic status so the row flips without waiting for SSE.
    for (const g of volumes.value) {
      for (const c of g.chapters) {
        if (c.providerChapterId === providerChapterId && c.status === "available") {
          c.status = "queued";
        }
      }
    }
  } catch (e) {
    toast(e instanceof Error ? e.message : "Couldn't queue download", "error");
  } finally {
    done?.();
  }
}
async function downloadAll(done?: () => void): Promise<void> {
  if (!series.value) {
    done?.();
    return;
  }
  try {
    await queueDownload(series.value.id);
    toast("Downloading available chapters…");
  } catch (e) {
    toast(e instanceof Error ? e.message : "Couldn't queue download", "error");
  } finally {
    done?.();
  }
}

async function onDeleteChapter(chapterId: string, done?: () => void): Promise<void> {
  if (!series.value) {
    done?.();
    return;
  }
  try {
    const result = await deleteChapterLocal(chapterId);
    toast(
      result.redownloadable
        ? "Download removed — chapter can be re-downloaded"
        : "Chapter permanently deleted",
      "info",
    );
    await load(series.value.id, { soft: true });
  } catch (e) {
    toast(e instanceof Error ? e.message : "Couldn't delete chapter", "error");
  } finally {
    done?.();
  }
}

function toggleFavorite(): void {
  if (!series.value) return;
  favorite.value = !favorite.value;
  void patchSeries(series.value.id, { favorite: favorite.value });
}
function setStatus(status: LibraryStatus): void {
  if (!series.value) return;
  libraryStatus.value = status;
  void patchSeries(series.value.id, { libraryStatus: status });
}
function setRating(n: number): void {
  if (!series.value) return;
  userRating.value = n;
  void patchSeries(series.value.id, { rating: n });
}
function clearRating(): void {
  if (!series.value) return;
  userRating.value = null;
  void patchSeries(series.value.id, { rating: null });
}

// --- Edit metadata ---
const editOpen = ref(false);
function onEdited(): void {
  editOpen.value = false;
  if (series.value) void load(series.value.id);
}

// --- Metadata: match to MangaDex + refresh ---
const isMatched = computed(() => !!series.value?.provider);
const chaptersSynced = computed(() => !!series.value?.chaptersSyncedAt);
const matchOpen = ref(false);
function openMatch(): void {
  if (!series.value) return;
  matchOpen.value = true;
}
function onMatched(): void {
  matchOpen.value = false;
  toast("Matched — fetching metadata…");
}
async function refreshMeta(): Promise<void> {
  if (!series.value) return;
  await refreshSeries(series.value.id);
  toast("Refreshing metadata…");
}
async function unlinkMeta(): Promise<void> {
  if (!series.value) return;
  await unlinkMatch(series.value.id);
  await load(series.value.id);
  toast("Unlinked source", "info");
}

// Reload when metadata or download tasks finish.
const disposeTask = onTaskDone((task) => {
  if (!series.value) return;
  if (task.kind === "metadata" || task.kind === "download") {
    void load(series.value.id, { soft: true });
  }
});
onUnmounted(disposeTask);

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
/** Track button: show current shelf label, or "Track" when untracked. */
const trackLabel = computed(() =>
  libraryStatus.value === "none" ? "Track" : statusLabel.value,
);
const cap = (s: string): string => s.charAt(0).toUpperCase() + s.slice(1);
</script>

<template>
  <div class="flex flex-col gap-6">
    <ErrorState v-if="failed" message="Couldn't load this series." @retry="reload" />
    <div v-else-if="loading && !series" class="flex justify-center py-20">
      <span class="loading loading-spinner loading-lg text-primary" />
    </div>
    <template v-else-if="series">
    <!-- HERO -->
    <section class="relative">
      <!-- Blurred backdrop, clipped here so it can't bleed but the dropdowns above still overflow. -->
      <div class="absolute inset-0 overflow-hidden">
        <img
          :src="series.coverUrl"
          alt=""
          aria-hidden="true"
          class="absolute inset-0 h-full w-full object-cover opacity-30 blur-3xl"
        />
        <div class="absolute inset-0 bg-base-200/70"></div>
      </div>

      <div class="relative flex flex-col gap-4 p-4 sm:flex-row sm:gap-6 sm:p-6">
        <CoverImage
          :src="series.coverUrl"
          :alt="series.title"
          priority
          class="cover w-36 shrink-0 rounded-box shadow-lg sm:w-48"
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
              <span
                v-if="series.rating"
                class="tooltip flex items-center gap-1"
                data-tip="Community rating (MangaDex)"
              >
                <Star class="size-3.5 fill-current text-warning" />
                <span class="font-medium text-base-content/80">{{ series.rating.toFixed(2) }}</span>
              </span>
              <span class="badge badge-sm" :class="contentRatingClass[series.contentRating]">
                {{ contentRatingLabel[series.contentRating] }}
              </span>
            </div>
          </div>

          <!-- Synopsis (Markdown + structured Namespace/Tags table from MangaDex) -->
          <div v-if="series.description">
            <SeriesDescription
              :text="series.description"
              :clamp="!expanded"
              :show-tag-table="expanded"
            />
            <button class="btn btn-ghost btn-xs mt-1" @click="expanded = !expanded">
              {{ expanded ? "Show less" : "Show more" }}
            </button>
          </div>

          <!-- Action row: left tools · right: new-count + track + metadata -->
          <div class="mt-auto flex flex-wrap items-center gap-2">
            <div class="flex flex-wrap items-center gap-2">
              <RouterLink :to="`/read/${series.id}`" class="btn btn-primary btn-sm gap-2">
                <BookOpen class="size-4" />
                Start reading
              </RouterLink>

              <!-- Your rating (1–10) -->
              <div class="dropdown">
                <div tabindex="0" role="button" class="btn btn-sm gap-1">
                  <Star class="size-4" :class="userRating ? 'fill-current text-warning' : ''" />
                  {{ userRating ? `${userRating}/10` : "Rate" }}
                </div>
                <div tabindex="0" class="dropdown-content z-10 mt-1 rounded-box bg-base-100 p-3 shadow">
                  <div class="mb-1 text-xs text-base-content/60">Your rating</div>
                  <div class="flex items-center gap-0.5" @mouseleave="hoverRating = 0">
                    <button
                      v-for="n in 10"
                      :key="n"
                      class="p-0.5"
                      :aria-label="`Rate ${n} of 10`"
                      @mouseenter="hoverRating = n"
                      @click="setRating(n)"
                    >
                      <Star
                        class="size-4"
                        :class="(hoverRating || userRating || 0) >= n ? 'fill-current text-warning' : 'text-base-content/30'"
                      />
                    </button>
                  </div>
                  <button v-if="userRating" class="btn btn-ghost btn-xs mt-2 w-full" @click="clearRating">
                    Clear rating
                  </button>
                </div>
              </div>

              <!-- Favorite -->
              <button
                class="btn btn-square btn-sm"
                :class="{ 'text-error': favorite }"
                aria-label="Favorite"
                @click="toggleFavorite"
              >
                <Heart class="size-4" :class="{ 'fill-current': favorite }" />
              </button>

              <!-- Add to list -->
              <AddToListMenu :series-id="series.id" />

              <!-- Edit metadata -->
              <button class="btn btn-sm gap-2" @click="editOpen = true">
                <Pencil class="size-4" />Edit
              </button>
            </div>

            <!-- Right cluster: new badge + Track (shelf) + metadata source -->
            <div class="ml-auto flex flex-wrap items-center gap-2">
              <span
                v-if="(series.availableChapters ?? 0) > 0"
                class="badge badge-warning gap-1"
                :title="`${series.availableChapters} new chapters available upstream`"
              >
                {{ series.availableChapters }} new
              </span>
              <div class="join">
                <!-- Track = shelf status -->
                <div class="dropdown dropdown-end">
                  <div
                    tabindex="0"
                    role="button"
                    class="btn btn-sm join-item gap-1.5"
                    :class="libraryStatus !== 'none' ? 'btn-primary' : ''"
                  >
                    <BookMarked class="size-4" />{{ trackLabel }}
                  </div>
                  <ul
                    tabindex="0"
                    class="menu dropdown-content z-10 mt-1 w-44 rounded-box bg-base-100 p-2 shadow"
                  >
                    <li v-for="s in statuses" :key="s.value">
                      <a
                        :class="{ 'menu-active': s.value === libraryStatus }"
                        @click="setStatus(s.value)"
                      >
                        {{ s.label === "None" ? "Not tracking" : s.label }}
                      </a>
                    </li>
                  </ul>
                </div>
                <div class="dropdown dropdown-end">
                  <div
                    tabindex="0"
                    role="button"
                    class="btn btn-square btn-sm join-item tooltip tooltip-bottom"
                    data-tip="Metadata source"
                    aria-label="Metadata source"
                  >
                    <RefreshCw class="size-4" />
                  </div>
                  <ul tabindex="0" class="menu dropdown-content z-10 mt-1 w-56 rounded-box bg-base-100 p-2 shadow">
                    <li><a @click="openMatch"><Link2 class="size-4" />Match on MangaDex…</a></li>
                    <li :class="{ 'menu-disabled': !isMatched }">
                      <a @click="isMatched && refreshMeta()"><RefreshCw class="size-4" />Refresh metadata</a>
                    </li>
                    <li v-if="isMatched">
                      <a class="text-error" @click="unlinkMeta"><X class="size-4" />Unlink source</a>
                    </li>
                  </ul>
                </div>
              </div>
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
        <ChapterList
          :volumes="volumes"
          :related="related"
          :art-covers="artCovers"
          :series-id="series.id"
          :matched="isMatched"
          :synced="chaptersSynced"
          :language="chapterLanguage"
          :order="chapterOrder"
          @download="downloadChapter"
          @download-all="downloadAll"
          @delete-chapter="onDeleteChapter"
          @update:language="onLanguageChange"
          @update:order="onOrderChange"
        />
      </div>
    </div>

    <!-- Match-on-MangaDex modal -->
    <MatchSeriesModal
      v-if="matchOpen && series"
      :series-id="series.id"
      :initial-query="series.title"
      @close="matchOpen = false"
      @matched="onMatched"
    />

    <!-- Edit metadata modal -->
    <EditSeriesModal v-if="editOpen" :series="series" @close="editOpen = false" @saved="onEdited" />
    </template>
  </div>
</template>
