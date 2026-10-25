<script setup lang="ts">
// Settings → Sync: background sync/index job log with detailed progress (what file is
// being indexed or which manga is being pulled from where + any error), pause/resume/cancel
// controls. Resource settings live in Libraries.
import { AlertCircle, Globe, Pause, Play, RefreshCw, Square, X } from "@lucide/vue";
import { computed, onMounted, onUnmounted, reactive, ref } from "vue";

import PhaseProgress from "../../components/PhaseProgress.vue";
import OverallProgress from "../../components/OverallProgress.vue";

import type { SyncState } from "../../api/client";
import { onTaskDone, onTaskEvent } from "../../api/events";
import { relativeTime } from "../../api/format";
import {
  controlSync,
  fetchSyncState,
  runSync,
  setSyncAutoClearCompleted,
} from "../../api/settingsQueries";
import { toast } from "../../lib/toast";
import { compareSyncJobs } from "../../lib/transferOrder";

interface SyncJobRow {
  id: string;
  kind: string;
  title: string;
  source: string;
  status: string;
  progress: number;
  detail: string | null;
  error: string | null;
  phases: Record<string, Record<string, number>>;
}

const sync = reactive({
  lastSync: "never",
  newChapters: 0,
  syncing: false,
  paused: false,
});
const jobs = ref<SyncJobRow[]>([]);
const orderedJobs = computed(() => jobs.value.toSorted(compareSyncJobs));
const autoClear = ref(false);
const autoClearLoaded = ref(false);
const savingAutoClear = ref(false);

async function toggleAutoClear(event: Event): Promise<void> {
  const previous = autoClear.value;
  autoClear.value = (event.target as HTMLInputElement).checked;
  savingAutoClear.value = true;
  try {
    const updated = await setSyncAutoClearCompleted(autoClear.value);
    autoClear.value = updated.autoClearCompleted;
    applySyncState(updated);
  } catch (e) {
    autoClear.value = previous;
    toast(e instanceof Error ? e.message : "Couldn't save sync settings", "error");
  } finally {
    savingAutoClear.value = false;
  }
}

const statusLabel: Record<string, string> = {
  queued: "Queued",
  running: "Running",
  paused: "Paused",
  done: "Done",
  failed: "Failed",
  cancelled: "Cancelled",
  cancelling: "Cancelling…",
};
const statusBadge: Record<string, string> = {
  running: "badge-primary",
  queued: "badge-ghost",
  paused: "badge-warning",
  done: "badge-success",
  failed: "badge-error",
  cancelled: "badge-ghost",
  cancelling: "badge-warning",
};
const kindLabel: Record<string, string> = {
  scan: "Index",
  sync: "Sync",
  import: "Account",
};

const hasActive = computed(() =>
  jobs.value.some(
    (j) =>
      j.status === "queued" ||
      j.status === "running" ||
      j.status === "paused" ||
      j.status === "cancelling",
  ),
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
  if (!savingAutoClear.value) autoClear.value = data.autoClearCompleted;
  autoClearLoaded.value = true;
  sync.lastSync = data.lastSync ? relativeTime(data.lastSync) : "never";
  sync.newChapters = data.newChapters;
  sync.syncing = data.syncing;
  sync.paused = data.paused ?? false;
  jobs.value = (data.jobs ?? []).map((j) => ({
    id: j.id,
    kind: j.kind,
    title: j.title,
    source: j.source,
    status: j.status,
    progress: j.progress ?? 0,
    detail: j.detail ?? null,
    error: j.error ?? null,
    phases: j.phases ?? {},
  }));
}

async function loadSync(): Promise<void> {
  applySyncState(await fetchSyncState());
}

async function syncNow(): Promise<void> {
  sync.syncing = true;
  try {
    await runSync();
    toast("Checking for new chapters…");
    await loadSync();
  } catch (e) {
    sync.syncing = false;
    toast(e instanceof Error ? e.message : "Couldn’t start sync", "error");
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
      <h3 class="text-xs font-semibold uppercase tracking-wide text-base-content/50">Sync</h3>
      <div class="card bg-base-100">
        <div class="card-body p-4">
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
        </div>
      </div>
    </section>

    <section class="flex flex-col gap-3">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <h3 class="text-xs font-semibold uppercase tracking-wide text-base-content/50">
          Sync jobs
        </h3>
        <div class="flex flex-wrap items-center gap-1">
          <label
            class="mr-2 flex cursor-pointer items-center gap-2 text-xs"
            title="Remove successful entries automatically. Failed and cancelled entries stay visible."
          >
            <input
              type="checkbox"
              role="switch"
              class="toggle toggle-sm toggle-primary"
              aria-label="Auto-clear completed sync jobs"
              :checked="autoClear"
              :disabled="!autoClearLoaded || savingAutoClear"
              @change="toggleAutoClear"
            />
            Auto-clear completed
          </label>
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

      <div role="list" aria-label="Sync queue" class="flex flex-col gap-1.5">
        <div
          v-for="job in orderedJobs"
          :key="job.id"
          role="listitem"
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

            <PhaseProgress :phases="job.phases" />
            <OverallProgress
              v-if="['queued', 'running', 'paused', 'cancelling'].includes(job.status)"
              :progress="job.progress"
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
