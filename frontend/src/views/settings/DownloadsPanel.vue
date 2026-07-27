<script setup lang="ts">
// Settings → Downloads: the download queue + the MangaDex sync card. Owns its own
// SSE wiring — the table reloads on throttled download.* events and on sync.done.
import { Globe, Pause, Play, RefreshCw, Square, X } from "lucide-vue-next";
import { computed, onMounted, onUnmounted, reactive, ref } from "vue";

import { api } from "../../api/client";
import { onTaskDone, onTaskEvent } from "../../api/events";
import { relativeTime } from "../../api/format";
import type { components } from "../../api/schema";
import ConfirmDialog from "../../components/ConfirmDialog.vue";
import CoverImage from "../../components/CoverImage.vue";
import { toast } from "../../lib/toast";

interface DlRow {
  id: string;
  series: { coverUrl: string; title: string };
  chapter: string;
  status: string;
  progress: number;
  phase: string | null;
  detail: string | null;
  size: string;
}
const dl = ref<DlRow[]>([]);
const sync = reactive({ lastSync: "never", newChapters: 0, syncing: false });
const dlLabel: Record<string, string> = {
  downloading: "Downloading",
  queued: "Queued",
  paused: "Paused",
  done: "Done",
  failed: "Failed",
};
const dlBadge: Record<string, string> = {
  downloading: "badge-primary",
  queued: "badge-ghost",
  paused: "badge-warning",
  done: "badge-success",
  failed: "badge-error",
};
const hasDone = computed(() => dl.value.some((d) => d.status === "done"));
const hasQueued = computed(() => dl.value.some((d) => d.status === "queued"));
const hasPaused = computed(() => dl.value.some((d) => d.status === "paused"));
const hasActive = computed(() =>
  dl.value.some((d) => d.status === "queued" || d.status === "downloading" || d.status === "paused"),
);

function formatBytes(n: number | null | undefined): string {
  if (!n) return "—";
  return n >= 1e6 ? `${(n / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1e3))} KB`;
}
function mapRows(rows: components["schemas"]["DownloadTaskOut"][] | undefined): DlRow[] {
  return (rows ?? []).map((d) => ({
    id: d.id,
    series: { coverUrl: d.series.coverUrl, title: d.series.title },
    chapter: d.chapter,
    status: d.status,
    progress: d.progress,
    phase: d.phase ?? null,
    detail: d.detail ?? null,
    size: formatBytes(d.sizeBytes),
  }));
}

/** Label for the in-flight progress badge: Fetching / Encoding with optional page count. */
function progressLabel(d: DlRow): string {
  if (d.status !== "downloading") return dlLabel[d.status] ?? d.status;
  const phase =
    d.phase === "encoding" ? "Encoding" : d.phase === "fetching" ? "Fetching" : "Downloading";
  const pages = d.detail ? ` · ${d.detail}` : "";
  return `${phase}${pages} · ${d.progress}%`;
}
async function loadDownloads(): Promise<void> {
  const { data } = await api.GET("/api/downloads");
  dl.value = mapRows(data);
}
async function loadSync(): Promise<void> {
  const { data } = await api.GET("/api/sync");
  if (!data) return;
  sync.lastSync = data.lastSync ? relativeTime(data.lastSync) : "never";
  sync.newChapters = data.newChapters;
}
async function syncNow(): Promise<void> {
  sync.syncing = true;
  await api.POST("/api/sync"); // runs on the queue; state reloads on the sync task's done event
  toast("Checking for new chapters…");
}
async function retryDownload(d: DlRow): Promise<void> {
  await api.POST("/api/downloads/{task_id}/retry", { params: { path: { task_id: d.id } } });
  toast("Download queued"); // the list refreshes when the download.done event arrives
}
async function pauseDownload(d: DlRow): Promise<void> {
  const { data } = await api.POST("/api/downloads/{task_id}/pause", { params: { path: { task_id: d.id } } });
  if (data) dl.value = mapRows(data); // endpoint returns the refreshed list
}
async function resumeDownload(d: DlRow): Promise<void> {
  const { data } = await api.POST("/api/downloads/{task_id}/resume", { params: { path: { task_id: d.id } } });
  if (data) dl.value = mapRows(data); // resumed chapter drains on the queue; rows climb on download.* events
}
async function removeDownload(d: DlRow): Promise<void> {
  await api.DELETE("/api/downloads/{task_id}", { params: { path: { task_id: d.id } } });
  await loadDownloads();
}
async function clearDone(): Promise<void> {
  await api.POST("/api/downloads/clear-completed");
  await loadDownloads();
}

const cancelAllOpen = ref(false);

async function runBulkAction(action: "pause-all" | "cancel-all" | "resume-all"): Promise<void> {
  const { data, error, response } = await api.POST("/api/downloads", {
    body: { action },
  });
  if (error) {
    toast("Couldn't update downloads", "error");
    return;
  }
  // Bulk actions return the refreshed list (200); create returns 202 TaskOut.
  if (response.status === 200 && Array.isArray(data)) {
    dl.value = mapRows(data as components["schemas"]["DownloadTaskOut"][]);
  } else {
    await loadDownloads();
  }
  const msg =
    action === "pause-all"
      ? "Queued downloads paused"
      : action === "cancel-all"
        ? "Downloads cancelled"
        : "Paused downloads resumed";
  toast(msg);
}

function bulkAction(action: "pause-all" | "cancel-all" | "resume-all"): void {
  if (action === "cancel-all") {
    cancelAllOpen.value = true;
    return;
  }
  void runBulkAction(action);
}

function confirmCancelAll(): void {
  cancelAllOpen.value = false;
  void runBulkAction("cancel-all");
}

const disposeDone = onTaskDone((task) => {
  if (task.kind === "download") {
    void loadDownloads();
  } else if (task.kind === "sync") {
    sync.syncing = false;
    void loadSync();
    if (task.status === "done") toast(`Sync complete — ${(task.result?.newChapters as number) ?? 0} new`);
  }
});
// While a download runs, refresh the table on progress events (throttled) so rows
// climb mid-chapter rather than appearing only when the whole job finishes.
let dlReloadTimer: ReturnType<typeof setTimeout> | null = null;
const disposeProgress = onTaskEvent((event) => {
  if (!event.startsWith("download.") || dlReloadTimer !== null) return;
  dlReloadTimer = setTimeout(() => {
    dlReloadTimer = null;
    void loadDownloads();
  }, 400);
});
onUnmounted(() => {
  disposeDone();
  disposeProgress();
  if (dlReloadTimer !== null) clearTimeout(dlReloadTimer);
});
onMounted(() => {
  void loadDownloads();
  void loadSync();
});
</script>

<template>
  <div class="flex flex-col gap-6">
    <section class="flex flex-col gap-3">
      <h3 class="text-xs font-semibold uppercase tracking-wide text-base-content/50">Sync</h3>
      <div class="card bg-base-100">
        <div class="card-body gap-3 p-4">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div class="flex items-start gap-3">
              <Globe class="mt-0.5 size-5 shrink-0 text-primary" />
              <div>
                <div class="text-sm font-medium">MangaDex</div>
                <div class="text-xs text-base-content/60">
                  <template v-if="sync.syncing">Checking for new chapters…</template>
                  <template v-else>
                    Last synced {{ sync.lastSync }} · {{ sync.newChapters }} new chapters
                  </template>
                </div>
              </div>
            </div>
            <button class="btn btn-primary btn-sm gap-2" :disabled="sync.syncing" @click="syncNow">
              <RefreshCw class="size-4" :class="{ 'animate-spin': sync.syncing }" />
              {{ sync.syncing ? "Syncing…" : "Sync now" }}
            </button>
          </div>
        </div>
      </div>
    </section>

    <section class="flex flex-col gap-3">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <h3 class="text-xs font-semibold uppercase tracking-wide text-base-content/50">Downloads</h3>
        <div class="flex flex-wrap items-center gap-1">
          <button
            class="btn btn-ghost btn-sm gap-1"
            :disabled="!hasQueued"
            title="Pause all queued chapters"
            @click="bulkAction('pause-all')"
          >
            <Pause class="size-4" />Pause all
          </button>
          <button
            class="btn btn-ghost btn-sm gap-1"
            :disabled="!hasPaused"
            title="Resume all paused chapters"
            @click="bulkAction('resume-all')"
          >
            <Play class="size-4" />Resume all
          </button>
          <button
            class="btn btn-ghost btn-sm gap-1 text-error"
            :disabled="!hasActive"
            title="Cancel all downloads"
            @click="bulkAction('cancel-all')"
          >
            <Square class="size-4" />Cancel all
          </button>
          <button class="btn btn-ghost btn-sm" :disabled="!hasDone" @click="clearDone">Clear completed</button>
        </div>
      </div>
      <div class="flex flex-col gap-1.5">
        <div
          v-for="d in dl"
          :key="d.id"
          class="flex items-center gap-3 rounded-box surface-border bg-base-100 p-2.5"
        >
          <CoverImage :src="d.series.coverUrl" :alt="d.series.title" class="cover h-12 w-8 shrink-0 rounded" />
          <div class="min-w-0 grow">
            <div class="flex items-center gap-2">
              <span class="truncate text-sm font-medium">{{ d.series.title }}</span>
              <span class="shrink-0 text-xs text-base-content/60">{{ d.chapter }}</span>
            </div>
            <div class="mt-1 flex items-center gap-2 text-xs">
              <span class="badge badge-sm" :class="dlBadge[d.status]">
                {{ progressLabel(d) }}
              </span>
              <span class="text-base-content/50">{{ d.size }}</span>
            </div>
            <div v-if="d.status === 'downloading'" class="mt-1.5 flex flex-col gap-0.5">
              <div class="flex justify-between text-[10px] uppercase tracking-wide text-base-content/50">
                <span :class="d.phase === 'fetching' ? 'text-primary font-semibold' : ''">Fetch</span>
                <span :class="d.phase === 'encoding' ? 'text-primary font-semibold' : ''">Encode</span>
              </div>
              <progress class="progress progress-primary h-1.5 w-full" :value="d.progress" max="100" />
            </div>
          </div>
          <div class="flex shrink-0 items-center gap-1">
            <button
              v-if="d.status === 'queued'"
              class="btn btn-square btn-ghost btn-xs"
              aria-label="Pause"
              @click="pauseDownload(d)"
            >
              <Pause class="size-4" />
            </button>
            <button
              v-else-if="d.status === 'paused'"
              class="btn btn-square btn-ghost btn-xs"
              aria-label="Resume"
              @click="resumeDownload(d)"
            >
              <Play class="size-4" />
            </button>
            <button
              v-else-if="d.status === 'failed'"
              class="btn btn-square btn-ghost btn-xs"
              aria-label="Retry"
              @click="retryDownload(d)"
            >
              <RefreshCw class="size-4" />
            </button>
            <button class="btn btn-square btn-ghost btn-xs" aria-label="Remove" @click="removeDownload(d)">
              <X class="size-4" />
            </button>
          </div>
        </div>
        <p v-if="!dl.length" class="py-8 text-center text-sm text-base-content/50">No downloads.</p>
      </div>
    </section>

    <ConfirmDialog
      :open="cancelAllOpen"
      title="Cancel all downloads?"
      message="Cancel every active download and clear the queue? In-flight chapters will stop after the current work unit; this cannot be undone."
      confirm-label="Cancel all"
      danger
      @confirm="confirmCancelAll"
      @cancel="cancelAllOpen = false"
    />
  </div>
</template>
