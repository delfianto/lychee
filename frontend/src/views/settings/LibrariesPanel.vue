<script setup lang="ts">
// Settings → Libraries: the registered library roots + manual scan triggers.
// Owns the scan SSE handler (a background scan refreshes the list on done).
import { Library, Plus, RefreshCw } from "@lucide/vue";
import { computed, onMounted, onUnmounted, ref } from "vue";

import { activeTasks, onTaskDone } from "../../api/events";
import { relativeTime } from "../../api/format";
import {
  deleteLibrary,
  fetchLibraryRows,
  scanAllLibraries,
  scanLibrary,
} from "../../api/settingsQueries";
import { toast } from "../../lib/toast";
import ErrorState from "../../components/ErrorState.vue";
import { createStaleGuard } from "../../lib/staleGuard";
import AddLibraryModal from "./AddLibraryModal.vue";
import ThumbnailStorageCard from "./ThumbnailStorageCard.vue";

interface LibraryRow {
  id: string;
  name: string;
  path: string;
  series: number;
  lastScan: string;
  managed: boolean;
}
const libraries = ref<LibraryRow[]>([]);
const showAdd = ref(false);
const loading = ref(true);
const loadError = ref("");
const loadGuard = createStaleGuard();
// A scan runs in the background; disable the triggers while one is in flight.
const scanning = computed(() =>
  activeTasks.value.some((t) => t.kind === "scan" || t.kind === "thumbs"),
);
async function loadLibraries(): Promise<void> {
  const token = loadGuard.next();
  loading.value = true;
  loadError.value = "";
  try {
    const data = await fetchLibraryRows();
    if (!loadGuard.isCurrent(token)) return;
    libraries.value = data.map((l) => ({
      id: l.id,
      name: l.name,
      path: l.path,
      managed: /^[a-z][a-z0-9+.-]*:/i.test(l.path.trim()),
      series: l.seriesCount,
      lastScan: l.lastScan ? relativeTime(l.lastScan) : "never",
    }));
  } catch (e) {
    if (loadGuard.isCurrent(token))
      loadError.value = e instanceof Error ? e.message : "Couldn’t load libraries";
  } finally {
    if (loadGuard.isCurrent(token)) loading.value = false;
  }
}
async function scanAll(): Promise<void> {
  try {
    await scanAllLibraries();
    toast("Scan started");
  } catch (e) {
    toast(e instanceof Error ? e.message : "Couldn't start scan", "error");
  }
}
async function scanOne(id: string): Promise<void> {
  try {
    await scanLibrary(id);
    toast("Scan started");
  } catch (e) {
    toast(e instanceof Error ? e.message : "Couldn't start scan", "error");
  }
}
async function removeLibrary(id: string): Promise<void> {
  try {
    await deleteLibrary(id);
    await loadLibraries();
  } catch (e) {
    toast(e instanceof Error ? e.message : "Couldn't remove library", "error");
  }
}
async function onLibraryAdded(): Promise<void> {
  showAdd.value = false;
  await loadLibraries();
  toast("Library added");
}

const disposeDone = onTaskDone((task) => {
  if (task.kind === "scan") {
    void loadLibraries();
    toast(
      task.status === "done" ? "Scan complete" : `Scan failed: ${task.detail ?? "Unknown error"}`,
      task.status === "done" ? "success" : "error",
    );
    return;
  }
  if (task.kind === "thumbs") {
    void loadLibraries();
    if (task.status === "done") {
      const n = (task.result?.thumbsGenerated as number | undefined) ?? 0;
      toast(n > 0 ? `Generated ${n} gallery thumbnail(s)` : "Gallery thumbnails up to date");
    } else {
      toast("Thumbnail generation failed", "error");
    }
  }
});
onUnmounted(disposeDone);
onMounted(loadLibraries);
</script>

<template>
  <div class="flex flex-col gap-8">
    <section class="flex flex-col gap-3">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <h3 class="text-xs font-semibold uppercase tracking-wide text-base-content/50">
          Libraries
        </h3>
        <div class="flex gap-2">
          <button class="btn btn-ghost btn-sm gap-1" :disabled="scanning" @click="scanAll">
            <RefreshCw :class="['size-4', scanning && 'animate-spin']" />Scan all
          </button>
          <button class="btn btn-primary btn-sm gap-1" @click="showAdd = true">
            <Plus class="size-4" />Add library
          </button>
        </div>
      </div>
      <p v-if="loading && !libraries.length" role="status" class="text-sm text-base-content/60">
        Loading libraries…
      </p>
      <ErrorState v-if="loadError" :message="loadError" @retry="loadLibraries" />
      <p v-else-if="!loading && !libraries.length" class="text-sm text-base-content/60">
        No libraries yet. Add a library to get started.
      </p>
      <div class="grid gap-4 lg:grid-cols-2">
        <div v-for="lib in libraries" :key="lib.id" class="card bg-base-100">
          <div class="card-body flex-row flex-wrap items-center gap-4 p-4">
            <Library class="size-5 shrink-0 text-primary" />
            <div class="min-w-0 grow">
              <div class="font-medium">{{ lib.name }}</div>
              <div class="truncate font-mono text-xs text-base-content/60">{{ lib.path }}</div>
              <div class="text-xs text-base-content/50">
                {{ lib.series }} series
                <template v-if="lib.managed"> · Managed by account sync</template>
                <template v-else> · scanned {{ lib.lastScan }}</template>
              </div>
            </div>
            <button
              v-if="!lib.managed"
              class="btn btn-ghost btn-sm"
              :disabled="scanning"
              @click="scanOne(lib.id)"
            >
              Scan
            </button>
            <button
              v-if="!lib.managed"
              class="btn btn-ghost btn-sm text-error"
              @click="removeLibrary(lib.id)"
            >
              Remove
            </button>
          </div>
        </div>
      </div>

      <AddLibraryModal v-if="showAdd" @close="showAdd = false" @added="onLibraryAdded" />
    </section>

    <ThumbnailStorageCard />
  </div>
</template>
