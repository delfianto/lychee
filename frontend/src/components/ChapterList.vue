<script setup lang="ts">
import {
  Check,
  ChevronDown,
  Download,
  ExternalLink,
  Loader2,
  MessageSquare,
  Trash2,
} from "@lucide/vue";
import { computed, ref, watch } from "vue";
import { RouterLink } from "vue-router";

import type { ChapterAvailability } from "../api/queries";
import ChapterAvailabilityNotice from "./ChapterAvailabilityNotice.vue";
import type { Chapter, Series, VolumeGroup } from "../types";
import ConfirmDialog from "./ConfirmDialog.vue";
import SeriesRail from "./SeriesRail.vue";

const props = withDefaults(
  defineProps<{
    volumes: VolumeGroup[];
    related?: Series[];
    artCovers?: string[];
    /** Series id for queue-download actions (remote-only rows). */
    seriesId?: string;
    matched?: boolean;
    /** True once the provider's chapter feed has been fetched at least once — lets the
     *  empty state say "the provider has none" instead of "not synced yet". */
    synced?: boolean;
    availability?: ChapterAvailability;
    checking?: boolean;
    /** Current language filter ("" = preferred language) and chapter sort order — both are
     *  server-side (`GET .../chapters?language=&order=`), so changes must round-trip
     *  through the parent rather than being applied client-side to the loaded volumes. */
    language?: string;
    order?: "asc" | "desc";
  }>(),
  {
    related: () => [],
    artCovers: () => [],
    seriesId: undefined,
    matched: false,
    synced: false,
    language: "",
    order: "desc",
  },
);

const emit = defineEmits<{
  /** `done` must be called when the download request finishes (success or error). */
  download: [providerChapterId: string, done: () => void];
  downloadAll: [done: () => void];
  deleteChapter: [chapterId: string, done: () => void];
  markRead: [chapterIds: string[], completed: boolean, done: (success: boolean) => void];
  retry: [];
  "update:language": [language: string];
  "update:order": [order: "asc" | "desc"];
}>();

function toggleOrder(): void {
  emit("update:order", props.order === "desc" ? "asc" : "desc");
}

const selected = ref(new Set<string>());
const marking = ref(false);
const readableChapters = computed(() =>
  props.volumes.flatMap((volume) => volume.chapters).filter((chapter) => !!readId(chapter)),
);
function readId(chapter: Chapter): string | null {
  if (chapter.id) return chapter.id;
  return props.seriesId && chapter.providerChapterId
    ? `adhoc:${props.seriesId}:${chapter.providerChapterId}`
    : null;
}
watch(
  () => props.volumes,
  () => {
    const available = new Set(readableChapters.value.map((chapter) => readId(chapter)!));
    selected.value = new Set([...selected.value].filter((id) => available.has(id)));
  },
);
function toggleSelection(id: string): void {
  const next = new Set(selected.value);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  selected.value = next;
}
function selectAll(): void {
  selected.value =
    selected.value.size === readableChapters.value.length
      ? new Set()
      : new Set(readableChapters.value.map((chapter) => readId(chapter)!));
}
function markRead(completed: boolean, chapter?: Chapter): void {
  const ids = chapter
    ? [readId(chapter)!]
    : selected.value.size
      ? [...selected.value]
      : readableChapters.value.map((item) => readId(item)!);
  if (marking.value || !ids.length) return;
  marking.value = true;
  emit("markRead", ids, completed, (success) => {
    marking.value = false;
    if (success && !chapter) selected.value = new Set();
  });
}

const tabs = [
  { key: "chapters", label: "Chapters" },
  { key: "related", label: "Related" },
  { key: "art", label: "Art" },
] as const;
const tab = ref<"chapters" | "related" | "art">("chapters");

const busy = ref<Set<string>>(new Set());
const deleting = ref<Set<string>>(new Set());

/** Pending destructive delete — confirmed via in-app dialog (no window.confirm). */
const deleteOpen = ref(false);
const pendingDelete = ref<Chapter | null>(null);

function rowKey(c: Chapter): string {
  return c.id ?? c.providerChapterId ?? `${c.number}-${c.language}`;
}

function chapterReadLink(c: Chapter): string | null {
  if (c.id && c.status === "downloaded") return `/read/${c.id}`;
  if (c.providerChapterId && props.seriesId) {
    return `/read/adhoc:${props.seriesId}:${c.providerChapterId}`;
  }
  return c.id ? `/read/${c.id}` : null;
}

function canDownload(c: Chapter): boolean {
  return c.status === "available" || c.status === "failed";
}

function isInFlight(c: Chapter): boolean {
  return c.status === "queued" || c.status === "downloading" || c.status === "paused";
}

function isProviderManaged(c: Chapter): boolean {
  return !!c.providerChapterId;
}

function canDelete(c: Chapter): boolean {
  return c.status === "downloaded" && !!c.id;
}

function clearBusy(id: string): void {
  const next = new Set(busy.value);
  next.delete(id);
  busy.value = next;
}

function clearDeleting(id: string): void {
  const next = new Set(deleting.value);
  next.delete(id);
  deleting.value = next;
}

function onDownload(c: Chapter): void {
  if (!c.providerChapterId || !canDownload(c)) return;
  if (busy.value.has(c.providerChapterId)) return;
  const id = c.providerChapterId;
  busy.value = new Set(busy.value).add(id);
  emit("download", id, () => clearBusy(id));
}

const downloadAllBusy = ref(false);
function onDownloadAll(): void {
  if (downloadAllBusy.value) return;
  downloadAllBusy.value = true;
  emit("downloadAll", () => {
    downloadAllBusy.value = false;
  });
}

function requestDelete(c: Chapter): void {
  if (!c.id || !canDelete(c)) return;
  pendingDelete.value = c;
  deleteOpen.value = true;
}

function cancelDelete(): void {
  deleteOpen.value = false;
  pendingDelete.value = null;
}

function confirmDelete(): void {
  const c = pendingDelete.value;
  if (!c?.id) {
    cancelDelete();
    return;
  }
  const id = c.id;
  deleting.value = new Set(deleting.value).add(id);
  deleteOpen.value = false;
  pendingDelete.value = null;
  emit("deleteChapter", id, () => clearDeleting(id));
}

const deleteDialogTitle = () => {
  const c = pendingDelete.value;
  if (!c) return "Delete chapter";
  return isProviderManaged(c) ? "Remove download?" : "Delete chapter permanently?";
};

const deleteDialogMessage = () => {
  const c = pendingDelete.value;
  if (!c) return "";
  return isProviderManaged(c)
    ? `Remove local files for Ch. ${c.number}?\n\nThe chapter stays available from the provider and can be downloaded again. Series metadata is kept.`
    : `Permanently delete Ch. ${c.number}?\n\nThe chapter and its files will be removed from the library. This cannot be undone.`;
};

const deleteConfirmLabel = () => {
  const c = pendingDelete.value;
  if (!c) return "Delete";
  return isProviderManaged(c) ? "Remove download" : "Delete permanently";
};

const hasAvailable = () =>
  props.volumes.some((g) =>
    g.chapters.some((c) => c.status === "available" || c.status === "failed"),
  );

const hasAny = () => props.volumes.some((g) => g.chapters.length > 0);

const statusLabel: Record<string, string> = {
  available: "Available",
  queued: "Queued",
  downloading: "Downloading",
  paused: "Paused",
  failed: "Failed",
  downloaded: "",
};
</script>

<template>
  <div class="flex flex-col gap-3">
    <!-- Tabs -->
    <div role="tablist" class="tabs tabs-border">
      <button
        v-for="t in tabs"
        :key="t.key"
        type="button"
        role="tab"
        class="tab"
        :class="{ 'tab-active': tab === t.key }"
        @click="tab = t.key"
      >
        {{ t.label }}
      </button>
    </div>

    <!-- Chapters -->
    <template v-if="tab === 'chapters'">
      <div class="flex flex-wrap items-center gap-2">
        <select
          class="select select-bordered select-sm w-40"
          :value="language"
          aria-label="Filter by language"
          @change="emit('update:language', ($event.target as HTMLSelectElement).value)"
        >
          <option value="en">English</option>
          <option value="">Preferred language</option>
          <option
            v-for="code in (availability?.availableLanguages ?? []).filter((code) => code !== 'en')"
            :key="code"
            :value="code"
          >
            {{ code.toUpperCase() }}
          </option>
        </select>
        <button
          v-if="seriesId && hasAvailable()"
          class="btn btn-primary btn-sm gap-1.5"
          :disabled="downloadAllBusy"
          @click="onDownloadAll"
        >
          <Loader2 v-if="downloadAllBusy" class="size-4 animate-spin" />
          <Download v-else class="size-4" />Download available
        </button>
        <button class="btn btn-ghost btn-sm ml-auto gap-1" @click="toggleOrder">
          {{ order === "desc" ? "Newest" : "Oldest"
          }}<ChevronDown class="size-4" :class="{ 'rotate-180': order === 'asc' }" />
        </button>
      </div>

      <div
        v-if="seriesId && readableChapters.length"
        class="flex flex-wrap items-center gap-2 text-xs"
      >
        <label class="flex items-center gap-2"
          ><input
            type="checkbox"
            class="checkbox checkbox-xs"
            :disabled="marking"
            :checked="selected.size === readableChapters.length"
            aria-label="Select all chapters"
            @change="selectAll"
          />Select all</label
        >
        <span v-if="selected.size">{{ selected.size }} selected</span>
        <button class="btn btn-ghost btn-xs gap-1" :disabled="marking" @click="markRead(true)">
          <Check class="size-3.5" />{{ selected.size ? "Mark selected read" : "Mark all read" }}
        </button>
        <button class="btn btn-ghost btn-xs" :disabled="marking" @click="markRead(false)">
          {{ selected.size ? "Mark selected unread" : "Mark all unread" }}
        </button>
      </div>
      <ChapterAvailabilityNotice
        v-if="availability && (!hasAny() || availability.status === 'error')"
        :availability="availability"
        :checking="checking"
        @retry="emit('retry')"
      />
      <div v-else-if="!hasAny()" class="py-10 text-center text-sm text-base-content/60">
        <template v-if="matched"
          >Chapter availability has not been checked yet. Refresh the chapter list to check
          MangaDex.</template
        >
        <template v-else>No chapters in the library for this series.</template>
      </div>

      <div v-for="vg in volumes" :key="vg.volume ?? 'none'" class="flex flex-col gap-1">
        <div class="text-sm font-semibold text-base-content/70">
          {{ vg.volume === null ? "No Volume" : `Volume ${vg.volume}` }}
        </div>
        <div class="overflow-hidden rounded-box border border-base-300">
          <div
            v-for="c in vg.chapters"
            :key="rowKey(c)"
            class="flex items-center gap-2 border-b border-base-300 px-3 py-2 last:border-b-0 sm:gap-3"
            :class="[chapterReadLink(c) ? 'hover:bg-base-300/40' : '', c.read ? 'opacity-50' : '']"
          >
            <input
              v-if="seriesId && readId(c)"
              type="checkbox"
              class="checkbox checkbox-xs shrink-0"
              :disabled="marking"
              :checked="selected.has(readId(c)!)"
              :aria-label="`Select chapter ${c.number}`"
              @change="toggleSelection(readId(c)!)"
            />
            <component
              :is="chapterReadLink(c) ? RouterLink : 'div'"
              v-bind="chapterReadLink(c) ? { to: chapterReadLink(c)! } : {}"
              class="grid min-w-0 grow grid-cols-1 gap-1 sm:flex sm:items-center sm:gap-3"
            >
              <div class="flex min-w-0 items-center gap-2 sm:contents">
                <span
                  class="h-2 w-2 shrink-0 rounded-full"
                  :class="c.read || c.status !== 'downloaded' ? 'bg-base-300' : 'bg-primary'"
                />
                <span class="w-16 shrink-0 text-sm font-medium">{{
                  c.number === "Oneshot" ? "Oneshot" : `Ch. ${c.number}`
                }}</span>
                <span class="min-w-0 grow truncate text-sm">{{ c.title }}</span>
              </div>
              <div class="flex min-w-0 flex-wrap items-center gap-2 sm:contents">
                <span class="hidden text-xs text-base-content/60 sm:inline">{{ c.group }}</span>
                <span class="badge badge-ghost badge-sm uppercase">{{ c.language }}</span>
                <span
                  v-if="c.status && c.status !== 'downloaded'"
                  class="badge badge-sm capitalize"
                  :class="{
                    'badge-primary': c.status === 'downloading' || c.status === 'queued',
                    'badge-warning': c.status === 'paused',
                    'badge-error': c.status === 'failed',
                    'badge-outline': c.status === 'available',
                  }"
                >
                  <Loader2 v-if="c.status === 'downloading'" class="mr-0.5 size-3 animate-spin" />
                  {{ statusLabel[c.status] }}
                </span>
                <span
                  class="hidden w-16 shrink-0 text-right text-xs text-base-content/60 sm:inline"
                  >{{ c.uploadedAt }}</span
                >
                <span
                  class="hidden w-12 shrink-0 items-center justify-end gap-1 text-xs text-base-content/50 md:inline-flex"
                >
                  <MessageSquare class="size-3.5" />{{ c.comments }}
                </span>
              </div>
            </component>

            <a
              v-if="c.sourceUrl"
              :href="c.sourceUrl"
              target="_blank"
              rel="noopener noreferrer"
              class="btn btn-square btn-ghost btn-xs"
              :aria-label="`Open chapter ${c.number} on MangaDex`"
              @click.stop
              ><ExternalLink class="size-3.5"
            /></a>
            <button
              v-if="seriesId && readId(c)"
              class="btn btn-square btn-ghost btn-xs"
              :class="{ 'text-primary': c.read }"
              :disabled="marking"
              :aria-label="`Mark chapter ${c.number} ${c.read ? 'unread' : 'read'}`"
              :title="c.read ? 'Mark unread' : 'Mark read'"
              @click.stop="markRead(!c.read, c)"
            >
              <Check class="size-4" :class="c.read ? 'opacity-100' : 'opacity-40'" />
            </button>
            <button
              v-if="canDownload(c) && c.providerChapterId"
              class="btn btn-ghost btn-xs gap-1"
              :disabled="busy.has(c.providerChapterId) || isInFlight(c)"
              aria-label="Download chapter"
              @click.stop.prevent="onDownload(c)"
            >
              <Download class="size-3.5" />
            </button>

            <!-- Danger: remove local files (provider) or permanent delete (local) -->
            <button
              v-if="canDelete(c)"
              type="button"
              class="btn btn-outline btn-error btn-xs gap-1 border-error/40"
              :class="{ 'btn-disabled': c.id && deleting.has(c.id) }"
              :disabled="!!(c.id && deleting.has(c.id))"
              :title="
                isProviderManaged(c)
                  ? 'Remove download (can re-download)'
                  : 'Delete chapter permanently'
              "
              :aria-label="
                isProviderManaged(c)
                  ? `Remove download of chapter ${c.number}`
                  : `Permanently delete chapter ${c.number}`
              "
              @click.stop.prevent="requestDelete(c)"
            >
              <Loader2 v-if="c.id && deleting.has(c.id)" class="size-3.5 animate-spin" />
              <Trash2 v-else class="size-3.5" />
            </button>
          </div>
        </div>
      </div>
    </template>

    <!-- Related -->
    <template v-else-if="tab === 'related'">
      <SeriesRail v-if="related.length" :series="related" />
      <div v-else class="py-8 text-center text-sm text-base-content/60">No related series.</div>
    </template>

    <!-- Art -->
    <template v-else>
      <div v-if="artCovers.length" class="grid grid-cols-3 gap-2 sm:grid-cols-4 md:grid-cols-6">
        <img
          v-for="(c, i) in artCovers"
          :key="i"
          :src="c"
          :alt="`Related art ${i + 1}`"
          class="cover w-full rounded-box object-cover"
        />
      </div>
      <div v-else class="py-8 text-center text-sm text-base-content/60">No extra art.</div>
    </template>

    <ConfirmDialog
      :open="deleteOpen"
      :title="deleteDialogTitle()"
      :message="deleteDialogMessage()"
      :confirm-label="deleteConfirmLabel()"
      danger
      @confirm="confirmDelete"
      @cancel="cancelDelete"
    />
  </div>
</template>
