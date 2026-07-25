<script setup lang="ts">
// Settings → Local import: configure importing local container files/folders and
// transcoding their pages to AVIF — the enable toggle, page quality, and the
// filename→metadata token pattern — plus the import action itself. Config persists
// on change (watch → PATCH); imports run on the queue and report via SSE.
import { Bookmark, FileText, FolderInput, Gauge, HardDriveDownload, Save, X } from "lucide-vue-next";
import { computed, onMounted, onUnmounted, reactive, ref, watch } from "vue";

import { api } from "../../api/client";
import { activeTasks, onTaskDone } from "../../api/events";
import { toast } from "../../lib/toast";

const config = reactive({ enabled: false, quality: 75, filenamePattern: "" });
const presets = ref<{ name: string; pattern: string }[]>([]);
const presetName = ref("");
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
    presets.value = data.patternPresets;
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
// Presets are saved patterns (server-side, in the import config) you can reuse.
async function savePresets(): Promise<void> {
  await api.PATCH("/api/import/config", { body: { patternPresets: presets.value } });
}
function savePreset(): void {
  const name = presetName.value.trim();
  if (!name || !config.filenamePattern.trim()) return;
  const preset = { name, pattern: config.filenamePattern };
  const idx = presets.value.findIndex((p) => p.name === name);
  if (idx >= 0) presets.value[idx] = preset; // overwrite same-named
  else presets.value.push(preset);
  presetName.value = "";
  void savePresets();
  toast(`Saved preset “${name}”`);
}
function applyPreset(preset: { name: string; pattern: string }): void {
  config.filenamePattern = preset.pattern; // the config watch persists the active pattern
}
function deletePreset(name: string): void {
  presets.value = presets.value.filter((p) => p.name !== name);
  void savePresets();
}
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
async function uploadFiles(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement;
  const files = [...(input.files ?? [])];
  if (files.length === 0) return;
  const form = new FormData();
  for (const file of files) form.append("files", file); // one batch → one series
  form.append("kind", importForm.kind);
  // Raw fetch (multipart) rather than the JSON openapi-fetch client.
  const resp = await fetch("/api/import/upload", { method: "POST", body: form });
  input.value = ""; // allow re-picking the same file(s)
  if (!resp.ok) {
    toast("Upload failed — check the file type/size and that import is enabled", "error");
    return;
  }
  toast(files.length === 1 ? "Upload started…" : `Uploading ${files.length} files…`);
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
        their pages to AVIF. Configure it on the left, then import from a path or upload files.
      </p>
      <div class="grid gap-4 lg:grid-cols-2 lg:items-start">
        <!-- Config -->
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
                <code class="text-primary/70">{language}</code> <code class="text-primary/70">{tags}</code>
                · <code class="text-primary/70">*</code> ignores a segment
              </p>
              <!-- Saved pattern presets (reusable, stored server-side with the config) -->
              <div class="mt-1 flex flex-col gap-1.5 border-t border-base-content/10 pt-3">
                <div class="flex items-center gap-1.5 text-xs font-medium text-base-content/60">
                  <Bookmark class="size-3.5" />Presets
                </div>
                <div v-if="presets.length" class="flex flex-col gap-1">
                  <div
                    v-for="p in presets"
                    :key="p.name"
                    class="group flex items-center gap-2 rounded-md border border-base-content/10 px-2.5 py-1.5 transition hover:border-primary/50 hover:bg-base-200/40"
                  >
                    <button class="min-w-0 flex-1 text-left" @click="applyPreset(p)">
                      <div class="flex items-center gap-2">
                        <span class="truncate text-sm font-medium">{{ p.name }}</span>
                        <span v-if="config.filenamePattern === p.pattern" class="badge badge-primary badge-xs">active</span>
                      </div>
                      <div class="truncate font-mono text-xs text-base-content/50">{{ p.pattern }}</div>
                    </button>
                    <button
                      class="btn btn-ghost btn-xs btn-circle text-base-content/40 opacity-0 transition hover:text-error group-hover:opacity-100"
                      aria-label="Delete preset"
                      @click="deletePreset(p.name)"
                    >
                      <X class="size-3.5" />
                    </button>
                  </div>
                </div>
                <p v-else class="text-xs text-base-content/40">No presets yet — name the pattern above to reuse it.</p>
                <div class="mt-0.5 flex gap-2">
                  <input
                    v-model="presetName"
                    type="text"
                    placeholder="Name this pattern"
                    class="input input-bordered input-xs flex-1"
                    @keyup.enter="savePreset"
                  />
                  <button
                    class="btn btn-primary btn-xs gap-1"
                    :disabled="!presetName.trim() || !config.filenamePattern.trim()"
                    @click="savePreset"
                  >
                    <Save class="size-3.5" />Save preset
                  </button>
                </div>
              </div>
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

            <div class="flex items-center gap-3 text-xs text-base-content/40">
              <div class="h-px flex-1 bg-base-content/10"></div>
              or upload files
              <div class="h-px flex-1 bg-base-content/10"></div>
            </div>
            <input
              type="file"
              accept=".cbz,.zip"
              multiple
              class="file-input file-input-bordered file-input-sm w-full"
              :disabled="!config.enabled"
              @change="uploadFiles"
            />
            <p class="text-xs text-base-content/40">Selecting several files imports them as one series.</p>

            <p v-if="!config.enabled" class="text-xs text-warning/80">Enable local import to use this.</p>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>
