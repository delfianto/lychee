<script setup lang="ts">
// Settings → Sync: background sync/index job log with detailed progress (what file is
// being indexed or which manga is being pulled from where + any error), pause/resume/cancel
// controls, and the parallel sync worker limiter (1–10).
import { AlertCircle, Gauge, Globe, Pause, Play, RefreshCw, Square, X } from "@lucide/vue";
import { computed, onMounted, onUnmounted, reactive, ref } from "vue";

import type { SyncState } from "../../api/client";
import { onTaskDone, onTaskEvent } from "../../api/events";
import { relativeTime } from "../../api/format";
import { controlSync, fetchSyncState, runSync, updateSyncConfig } from "../../api/settingsQueries";
import { toast } from "../../lib/toast";

interface SyncJobRow {
  id: string;
  kind: string;
  title: string;
  source: string;
  status: string;
  progress: number;
  detail: string | null;
  error: string | null;
}

const sync = reactive({
  lastSync: "never",
  newChapters: 0,
  syncing: false,
  paused: false,
  parallelSyncs: 1,
});
const jobs = ref<SyncJobRow[]>([]);

const statusLabel: Record<string, string> = {
  queued: "Queued",
  running: "Running",
  paused: "Paused",
  done: "Done",
  failed: "Failed",
  cancelled: "Cancelled",
};
const statusBadge: Record<string, string> = {
  running: "badge-primary",
  queued: "badge-ghost",
  paused: "badge-warning",
  done: "badge-success",
  failed: "badge-error",
  cancelled: "badge-ghost",
};
const kindLabel: Record<string, string> = {
  scan: "Index",
  sync: "Sync",
  import: "Account",
};

const hasActive = computed(() =>
  jobs.value.some((j) => j.status === "queued" || j.status === "running" || j.status === "paused"),
);
const hasRunningOrQueued = computed(() =>
  jobs.value.some((j) => j.status === "queued" || j.status === "running"),
);
const hasPaused = computed(() => sync.paused || jobs.value.some((j) => j.status === "paused"));
const hasFinished = computed(() =>
  jobs.value.some((j) => j.status === "done" || j.status === "failed" || j.status === "cancelled"),
);

function applySyncState(data: SyncState | null): void {
  if (!data) return;
  sync.lastSync = data.lastSync ? relativeTime(data.lastSync) : "never";
  sync.newChapters = data.newChapters;
  sync.syncing = data.syncing;
  sync.paused = data.paused ?? false;
  sync.parallelSyncs = data.parallelSyncs ?? 1;
  jobs.value = (data.jobs ?? []).map((j) => ({
    id: j.id,
    kind: j.kind,
    title: j.title,
    source: j.source,
    status: j.status,
    progress: j.progress ?? 0,
    detail: j.detail ?? null,
    error: j.error ?? null,
  }));
}

async function loadSync(): Promise<void> {
  applySyncState(await fetchSyncState());
}

async function syncNow(): Promise<void> {
  sync.syncing = true;
  await runSync();
  toast("Checking for new chapters…");
  await loadSync();
}

async function setParallelSyncs(raw: number): Promise<void> {
  const clamped = Math.max(1, Math.min(10, Math.round(Number.isFinite(raw) ? raw : 1)));
  sync.parallelSyncs = clamped;
  try {
    const updated = await updateSyncConfig(clamped);
    applySyncState(updated);
    toast(`Parallel sync jobs set to ${sync.parallelSyncs}`);
  } catch (e) {
    toast(e instanceof Error ? e.message : "Couldn't update sync settings", "error");
  }
}

async function runControl(action: string, jobId?: string): Promise<void> {
  try {
    const updated = await controlSync(action, jobId);
    applySyncState(updated);
    if (action === "pause-all" || action === "pause") toast("Sync paused");
    else if (action === "resume-all" || action === "resume") toast("Sync resumed");
    else if (action === "cancel-all" || action === "cancel") toast("Sync cancelled");
  } catch (e) {
    toast(e instanceof Error ? e.message : "Couldn't update sync job", "error");
  }
}

const disposeDone = onTaskDone((task) => {
  if (task.kind === "sync" || task.kind === "scan" || task.kind === "import") {
    void loadSync();
  }
});
let reloadTimer: ReturnType<typeof setTimeout> | null = null;
const disposeProgress = onTaskEvent((event) => {
  if (
    (!event.startsWith("sync.") && !event.startsWith("scan.") && !event.startsWith("import.")) ||
    reloadTimer !== null
  ) {
    return;
  }
  reloadTimer = setTimeout(() => {
    reloadTimer = null;
    void loadSync();
  }, 300);
});

onUnmounted(() => {
  disposeDone();
  disposeProgress();
  if (reloadTimer !== null) clearTimeout(reloadTimer);
});
onMounted(() => {
  void loadSync();
});
</script>

<template>
  <div class="flex flex-col gap-6">
    <section class="flex flex-col gap-3">
      <h3 class="text-xs font-semibold uppercase tracking-wide text-base-content/50">
        Sync configuration
      </h3>
      <div class="card bg-base-100">
        <div class="card-body gap-3 p-4">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div class="flex items-start gap-3">
              <Globe class="mt-0.5 size-5 shrink-0 text-primary" />
              <div>
                <div class="text-sm font-medium">Background sync</div>
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

          <div
            class="flex flex-wrap items-center justify-between gap-3 border-t border-base-content/10 pt-3"
          >
            <div class="flex items-start gap-3">
              <Gauge class="mt-0.5 size-5 shrink-0 text-primary" />
              <div>
                <div class="text-sm font-medium">Parallel sync jobs</div>
                <div class="text-xs text-base-content/50">
                  Concurrent sync &amp; indexing workers (min 1, max 10)
                </div>
              </div>
            </div>
            <input
              type="number"
              min="1"
              max="10"
              :value="sync.parallelSyncs"
              aria-label="Parallel sync jobs"
              class="input input-bordered input-sm w-20 text-right tabular-nums"
              @change="setParallelSyncs(Number(($event.target as HTMLInputElement).value))"
            />
          </div>
        </div>
      </div>
    </section>

    <section class="flex flex-col gap-3">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <h3 class="text-xs font-semibold uppercase tracking-wide text-base-content/50">
          Sync jobs
        </h3>
        <div class="flex flex-wrap items-center gap-1">
          <button
            class="btn btn-ghost btn-sm gap-1"
            :disabled="!hasRunningOrQueued"
            @click="runControl('pause-all')"
          >
            <Pause class="size-4" />Pause all
          </button>
          <button
            class="btn btn-ghost btn-sm gap-1"
            :disabled="!hasPaused"
            @click="runControl('resume-all')"
          >
            <Play class="size-4" />Resume all
          </button>
          <button
            class="btn btn-ghost btn-sm gap-1 text-error"
            :disabled="!hasActive"
            @click="runControl('cancel-all')"
          >
            <Square class="size-4" />Cancel all
          </button>
          <button
            class="btn btn-ghost btn-sm"
            :disabled="!hasFinished"
            @click="runControl('clear-completed')"
          >
            Clear completed
          </button>
        </div>
      </div>

      <div class="flex flex-col gap-1.5">
        <div
          v-for="job in jobs"
          :key="job.id"
          class="flex items-start gap-3 rounded-box surface-border bg-base-100 p-3"
        >
          <div class="min-w-0 grow">
            <div class="flex flex-wrap items-center gap-2">
              <span class="badge badge-outline badge-xs uppercase">
                {{ kindLabel[job.kind] ?? job.kind }}
              </span>
              <span class="truncate text-sm font-medium">{{ job.title }}</span>
              <span class="truncate font-mono text-xs text-base-content/60">
                from {{ job.source }}
              </span>
              <span class="badge badge-sm ml-auto" :class="statusBadge[job.status]">
                {{ statusLabel[job.status] ?? job.status }}
              </span>
            </div>

            <div v-if="job.detail" class="mt-1 text-xs text-base-content/70">
              {{ job.detail }}
            </div>

            <div
              v-if="job.error"
              class="mt-1 flex items-center gap-1.5 text-xs text-error"
              role="alert"
            >
              <AlertCircle class="size-3.5 shrink-0" />
              <span>{{ job.error }}</span>
            </div>

            <progress
              v-if="job.status === 'running' || job.status === 'paused'"
              class="progress progress-primary mt-2 h-1.5 w-full"
              :value="job.progress"
              max="100"
            />
          </div>

          <div class="flex shrink-0 items-center gap-1">
            <button
              v-if="job.status === 'queued' || job.status === 'running'"
              class="btn btn-square btn-ghost btn-xs"
              aria-label="Pause job"
              @click="runControl('pause', job.id)"
            >
              <Pause class="size-4" />
            </button>
            <button
              v-else-if="job.status === 'paused'"
              class="btn btn-square btn-ghost btn-xs"
              aria-label="Resume job"
              @click="runControl('resume', job.id)"
            >
              <Play class="size-4" />
            </button>
            <button
              v-if="job.status === 'queued' || job.status === 'running' || job.status === 'paused'"
              class="btn btn-square btn-ghost btn-xs text-error"
              aria-label="Cancel job"
              @click="runControl('cancel', job.id)"
            >
              <X class="size-4" />
            </button>
          </div>
        </div>
        <p v-if="!jobs.length" class="py-8 text-center text-sm text-base-content/50">
          No sync jobs.
        </p>
      </div>
    </section>
  </div>
</template>
