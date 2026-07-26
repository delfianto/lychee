<script setup lang="ts">
import { ChevronDown, Download, Loader2, MessageSquare, Trash2 } from "lucide-vue-next";
import { ref } from "vue";
import { RouterLink } from "vue-router";

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
  }>(),
  {
    related: () => [],
    artCovers: () => [],
    seriesId: undefined,
    matched: false,
  },
);

const emit = defineEmits<{
  /** `done` must be called when the download request finishes (success or error). */
  download: [providerChapterId: string, done: () => void];
  downloadAll: [done: () => void];
  deleteChapter: [chapterId: string, done: () => void];
}>();

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
  props.volumes.some((g) => g.chapters.some((c) => c.status === "available" || c.status === "failed"));

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
      <a
        v-for="t in tabs"
        :key="t.key"
        role="tab"
        class="tab"
        :class="{ 'tab-active': tab === t.key }"
        @click="tab = t.key"
      >
        {{ t.label }}
      </a>
    </div>

    <!-- Chapters -->
    <template v-if="tab === 'chapters'">
      <div class="flex items-center gap-2">
        <select class="select select-bordered select-sm w-40">
          <option>English</option>
          <option>All languages</option>
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
        <button class="btn btn-ghost btn-sm ml-auto gap-1">Newest<ChevronDown class="size-4" /></button>
      </div>

      <div v-if="!hasAny()" class="py-10 text-center text-sm text-base-content/60">
        <template v-if="matched">No chapters listed yet — try refreshing metadata or sync.</template>
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
            class="flex items-center gap-3 border-b border-base-300 px-3 py-2 last:border-b-0"
            :class="[
              c.id && c.status === 'downloaded' ? 'hover:bg-base-300/40' : '',
              c.read ? 'opacity-50' : '',
            ]"
          >
            <component
              :is="c.id && c.status === 'downloaded' ? RouterLink : 'div'"
              v-bind="c.id && c.status === 'downloaded' ? { to: `/read/${c.id}` } : {}"
              class="flex min-w-0 grow items-center gap-3"
            >
              <span
                class="h-2 w-2 shrink-0 rounded-full"
                :class="c.read || c.status !== 'downloaded' ? 'bg-base-300' : 'bg-primary'"
              />
              <span class="w-16 shrink-0 text-sm font-medium">Ch. {{ c.number }}</span>
              <span class="min-w-0 grow truncate text-sm">{{ c.title }}</span>
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
              <span class="hidden w-16 shrink-0 text-right text-xs text-base-content/60 sm:inline">{{
                c.uploadedAt
              }}</span>
              <span
                class="hidden w-12 shrink-0 items-center justify-end gap-1 text-xs text-base-content/50 md:inline-flex"
              >
                <MessageSquare class="size-3.5" />{{ c.comments }}
              </span>
            </component>

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
        <img v-for="(c, i) in artCovers" :key="i" :src="c" alt="" class="cover w-full rounded-box object-cover" />
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
