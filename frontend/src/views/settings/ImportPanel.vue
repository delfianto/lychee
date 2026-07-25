<script setup lang="ts">
// Settings → Local import: configure importing local container files/folders and
// transcoding their pages to AVIF — the enable toggle, page quality, and the
// filename→metadata token pattern — plus the import action itself. Config persists
// on change (watch → PATCH); imports run on the queue and report via SSE.
import { FileText, FolderInput, Gauge, HardDriveDownload } from "lucide-vue-next";
import { computed, onMounted, onUnmounted, reactive, watch } from "vue";

import { api } from "../../api/client";
import { activeTasks, onTaskDone } from "../../api/events";
import { toast } from "../../lib/toast";

const config = reactive({ enabled: false, quality: 75, filenamePattern: "" });
const qualityTiers = [
  { value: 85, label: "Higher quality" },
  { value: 75, label: "Balanced" },
  { value: 60, label: "Smaller files" },
];
let loaded = false;

const importForm = reactive({ path: "", kind: "manga" });
const importing = computed(() => activeTasks.value.some((t) => t.kind === "localimport"));

async function loadConfig(): Promise<void> {
  const { data } = await api.GET("/api/import/config");
  if (data) {
    config.enabled = data.enabled;
    config.quality = data.quality;
    config.filenamePattern = data.filenamePattern;
  }
}
watch(
  () => ({ ...config }),
  () => {
    if (!loaded) return;
    void api.PATCH("/api/import/config", {
      body: {
        enabled: config.enabled,
        quality: config.quality,
        filenamePattern: config.filenamePattern,
      },
    });
  },
);
async function startImport(): Promise<void> {
  const { error } = await api.POST("/api/import", {
    body: { path: importForm.path.trim(), kind: importForm.kind },
  });
  if (error) {
    toast("Import failed — check the path and that import is enabled", "error");
    return;
  }
  toast("Import started…"); // progress + result arrive via the localimport task's SSE
}
const disposeDone = onTaskDone((task) => {
  if (task.kind !== "localimport") return;
  if (task.status === "done") {
    toast(`Imported ${(task.result?.booksImported as number) ?? 0} book(s)`);
    importForm.path = "";
  } else if (task.status === "failed") {
    toast("Import failed", "error");
  }
});
onUnmounted(disposeDone);
onMounted(async () => {
  await loadConfig();
  loaded = true;
});
</script>

<template>
  <div class="flex flex-col gap-6">
    <section class="flex flex-col gap-3">
      <h3 class="text-xs font-semibold uppercase tracking-wide text-base-content/50">Local import</h3>
      <p class="max-w-2xl text-xs text-base-content/50">
        Import comic/manga containers (CBZ/ZIP) or image folders from the server's disk and transcode
        their pages to AVIF. Configure it here, then import from a path below.
      </p>
      <div class="card bg-base-100">
        <div class="card-body gap-4 p-4">
          <div class="flex items-center justify-between gap-4">
            <div class="flex items-start gap-3">
              <FolderInput class="mt-0.5 size-5 shrink-0 text-primary" />
              <div>
                <div class="text-sm font-medium">Enable local import</div>
                <div class="text-xs text-base-content/50">Allow importing &amp; transcoding local files</div>
              </div>
            </div>
            <input v-model="config.enabled" type="checkbox" class="toggle toggle-primary toggle-sm" />
          </div>

          <label class="flex items-center justify-between gap-4">
            <div class="flex items-start gap-3">
              <Gauge class="mt-0.5 size-5 shrink-0 text-primary" />
              <div>
                <div class="text-sm font-medium">Image quality</div>
                <div class="text-xs text-base-content/50">AVIF quality for transcoded pages</div>
              </div>
            </div>
            <select v-model.number="config.quality" class="select select-bordered select-sm w-40">
              <option v-for="t in qualityTiers" :key="t.value" :value="t.value">{{ t.label }}</option>
            </select>
          </label>

          <div class="flex flex-col gap-2">
            <div class="flex items-start gap-3">
              <FileText class="mt-0.5 size-5 shrink-0 text-primary" />
              <div>
                <div class="text-sm font-medium">Filename pattern</div>
                <div class="text-xs text-base-content/50">
                  Auto-fill metadata from filenames — leave blank to use the built-in parser
                </div>
              </div>
            </div>
            <input
              v-model="config.filenamePattern"
              class="input input-bordered input-sm w-full font-mono"
              placeholder="{series} - c{chapter} (v{volume})"
            />
            <p class="text-xs leading-relaxed text-base-content/40">
              Tokens:
              <code class="text-primary/70">{series}</code> <code class="text-primary/70">{title}</code>
              <code class="text-primary/70">{volume}</code> <code class="text-primary/70">{chapter}</code>
              <code class="text-primary/70">{author}</code> <code class="text-primary/70">{artist}</code>
              <code class="text-primary/70">{group}</code> <code class="text-primary/70">{year}</code>
              · <code class="text-primary/70">*</code> ignores a segment
            </p>
          </div>
        </div>
      </div>

      <!-- Import action -->
      <div class="card bg-base-100">
        <div class="card-body gap-3 p-4">
          <div class="flex items-start gap-3">
            <HardDriveDownload class="mt-0.5 size-5 shrink-0 text-primary" />
            <div>
              <div class="text-sm font-medium">Import from a path</div>
              <div class="text-xs text-base-content/50">A container file (.cbz/.zip) or a folder on the server</div>
            </div>
          </div>
          <div class="flex flex-col gap-2 sm:flex-row">
            <input
              v-model="importForm.path"
              class="input input-bordered input-sm flex-1 font-mono"
              placeholder="/data/incoming/Series   or   /data/file.cbz"
              :disabled="!config.enabled"
            />
            <select v-model="importForm.kind" class="select select-bordered select-sm sm:w-32" :disabled="!config.enabled">
              <option value="manga">Manga</option>
              <option value="comic">Comic</option>
              <option value="gallery">Gallery</option>
            </select>
            <button
              class="btn btn-primary btn-sm gap-1"
              :disabled="!config.enabled || !importForm.path.trim() || importing"
              @click="startImport"
            >
              <FolderInput class="size-4" />{{ importing ? "Importing…" : "Import" }}
            </button>
          </div>
          <p v-if="!config.enabled" class="text-xs text-warning/80">Enable local import above to use this.</p>
        </div>
      </div>
    </section>
  </div>
</template>
