<script setup lang="ts">
// Settings → Downloads: the download queue + the MangaDex sync card. Owns its own
// SSE wiring — the table reloads on throttled download.* events and on sync.done.
import { Globe, Pause, Play, RefreshCw, X } from "lucide-vue-next";
import { computed, onMounted, onUnmounted, reactive, ref } from "vue";

import { api } from "../../api/client";
import { onTaskDone, onTaskEvent } from "../../api/events";
import { relativeTime } from "../../api/format";
import { toast } from "../../lib/toast";

interface DlRow {
  id: string;
  series: { coverUrl: string; title: string };
  chapter: string;
  status: string;
  progress: number;
  size: string;
}
const dl = ref<DlRow[]>([]);
const sync = reactive({ lastSync: "never", newChapters: 0, autoEvery: "6h", syncing: false });
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
function formatBytes(n: number | null | undefined): string {
  if (!n) return "—";
  return n >= 1e6 ? `${(n / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1e3))} KB`;
}
async function loadDownloads(): Promise<void> {
  const { data } = await api.GET("/api/downloads");
  dl.value = (data ?? []).map((d) => ({
    id: d.id,
    series: { coverUrl: d.series.coverUrl, title: d.series.title },
    chapter: d.chapter,
    status: d.status,
    progress: d.progress,
    size: formatBytes(d.sizeBytes),
  }));
}
async function loadSync(): Promise<void> {
  const { data } = await api.GET("/api/sync");
  if (!data) return;
  sync.lastSync = data.lastSync ? relativeTime(data.lastSync) : "never";
  sync.newChapters = data.newChapters;
  sync.autoEvery = `${Math.max(1, Math.round(data.autoEveryMinutes / 60))}h`;
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
async function removeDownload(d: DlRow): Promise<void> {
  await api.DELETE("/api/downloads/{task_id}", { params: { path: { task_id: d.id } } });
  await loadDownloads();
}
async function clearDone(): Promise<void> {
  await api.POST("/api/downloads/clear-completed");
  await loadDownloads();
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
                    Last synced {{ sync.lastSync }} · {{ sync.newChapters }} new chapters · auto every
                    {{ sync.autoEvery }}
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
      <div class="flex items-center justify-between gap-2">
        <h3 class="text-xs font-semibold uppercase tracking-wide text-base-content/50">Downloads</h3>
        <button class="btn btn-ghost btn-sm" :disabled="!hasDone" @click="clearDone">Clear completed</button>
      </div>
      <div class="flex flex-col gap-1.5">
        <div
          v-for="d in dl"
          :key="d.id"
          class="flex items-center gap-3 rounded-box surface-border bg-base-100 p-2.5"
        >
          <img :src="d.series.coverUrl" :alt="d.series.title" class="cover h-12 shrink-0 rounded object-cover" />
          <div class="min-w-0 grow">
            <div class="flex items-center gap-2">
              <span class="truncate text-sm font-medium">{{ d.series.title }}</span>
              <span class="shrink-0 text-xs text-base-content/60">{{ d.chapter }}</span>
            </div>
            <div class="mt-1 flex items-center gap-2 text-xs">
              <span class="badge badge-sm" :class="dlBadge[d.status]">
                {{ d.status === "downloading" ? `Downloading ${d.progress}%` : dlLabel[d.status] }}
              </span>
              <span class="text-base-content/50">{{ d.size }}</span>
            </div>
            <progress
              v-if="d.status === 'downloading' || d.status === 'paused'"
              class="progress progress-primary mt-1.5 h-1"
              :value="d.progress"
              max="100"
            ></progress>
          </div>
          <div class="flex shrink-0 items-center gap-1">
            <button
              v-if="d.status === 'downloading'"
              class="btn btn-square btn-ghost btn-xs"
              aria-label="Pause"
              @click="d.status = 'paused'"
            >
              <Pause class="size-4" />
            </button>
            <button
              v-else-if="d.status === 'paused'"
              class="btn btn-square btn-ghost btn-xs"
              aria-label="Resume"
              @click="d.status = 'downloading'"
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
  </div>
</template>
