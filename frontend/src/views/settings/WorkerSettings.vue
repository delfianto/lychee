<script setup lang="ts">
import { Cpu, Gauge, RefreshCw } from "@lucide/vue";
import { computed, onMounted, reactive, ref } from "vue";
import { fetchWorkerSettings, saveWorkerSettings } from "../../api/settingsQueries";
import { toast } from "../../lib/toast";

const groups = [
  {
    kind: "io",
    title: "I/O workers",
    icon: Gauge,
    help: "Network and filesystem concurrency",
    fields: [
      {
        key: "downloadWorkers",
        label: "Download workers",
        help: "Parallel file requests within a chapter",
        max: 10,
      },
      {
        key: "scanMetadataWorkers",
        label: "Scan/metadata I/O workers",
        help: "One shared budget across scans and metadata requests",
        max: 10,
      },
    ],
  },
  {
    kind: "image",
    title: "Image processing",
    icon: Cpu,
    help: "Separate limits for conversion and thumbnail workers",
    fields: [
      { key: "conversionWorkers", label: "Conversion workers", help: "Pages and imports", max: 64 },
      {
        key: "thumbnailWorkers",
        label: "Thumbnail workers",
        help: "Covers and gallery previews",
        max: 64,
      },
    ],
  },
] as const;
const fields = groups.flatMap((group) => [...group.fields]);
const config = ref<Awaited<ReturnType<typeof fetchWorkerSettings>> | null>(null);
const draft = reactive({
  downloadWorkers: 1,
  scanMetadataWorkers: 1,
  conversionWorkers: 1,
  thumbnailWorkers: 1,
});
const loading = ref(true);
const saving = ref(false);
const detecting = ref(false);
const error = ref("");
const busy = computed(() => saving.value || detecting.value);
const valid = computed(() =>
  fields.every(
    (field) =>
      Number.isInteger(draft[field.key]) && draft[field.key] >= 1 && draft[field.key] <= field.max,
  ),
);
const dirty = computed(
  () => !!config.value && fields.some((field) => draft[field.key] !== config.value![field.key]),
);
function apply(next: Awaited<ReturnType<typeof fetchWorkerSettings>>): void {
  config.value = next;
  for (const field of fields) draft[field.key] = next[field.key];
}
async function load(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    apply(await fetchWorkerSettings());
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Could not load worker settings";
  } finally {
    loading.value = false;
  }
}
async function detect(): Promise<void> {
  if (!config.value || busy.value) return;
  detecting.value = true;
  error.value = "";
  try {
    const detected = await fetchWorkerSettings();
    config.value = {
      ...config.value,
      cpuThreads: detected.cpuThreads,
      recommendedConversionWorkers: detected.recommendedConversionWorkers,
      recommendedThumbnailWorkers: detected.recommendedThumbnailWorkers,
    };
    draft.conversionWorkers = detected.recommendedConversionWorkers;
    draft.thumbnailWorkers = detected.recommendedThumbnailWorkers;
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Could not detect worker settings";
  } finally {
    detecting.value = false;
  }
}
async function save(): Promise<void> {
  if (!valid.value || !dirty.value || busy.value) return;
  saving.value = true;
  error.value = "";
  try {
    apply(await saveWorkerSettings({ ...draft }));
    toast("Worker settings saved");
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Could not save worker settings";
  } finally {
    saving.value = false;
  }
}
onMounted(load);
</script>

<template>
  <form class="divide-y divide-base-content/10" aria-label="Worker settings" @submit.prevent="save">
    <p v-if="loading" class="px-4 py-3 text-xs text-base-content/60" role="status">
      Loading worker settings…
    </p>
    <template v-if="config">
      <div v-for="group in groups" :key="group.kind" class="settings-row">
        <div class="flex items-start gap-3">
          <component :is="group.icon" class="mt-0.5 size-5 shrink-0 text-primary" />
          <div>
            <h4 class="text-sm font-medium">{{ group.title }}</h4>
            <p class="mt-1 text-xs text-base-content/50">{{ group.help }}</p>
          </div>
        </div>
        <div class="flex min-w-0 flex-col gap-3 xl:col-span-2">
          <div class="grid gap-3 sm:grid-cols-2">
            <label
              v-for="field in group.fields"
              :key="field.key"
              class="flex min-w-0 items-center justify-between gap-3 rounded-md bg-base-200/50 px-3 py-2"
            >
              <span class="min-w-0 text-xs">
                <span class="block font-medium">{{ field.label }}</span>
                <span class="mt-0.5 block text-base-content/50">{{ field.help }}</span>
              </span>
              <input
                v-model.number="draft[field.key]"
                type="number"
                min="1"
                :max="field.max"
                step="1"
                class="input input-bordered input-sm w-20 shrink-0"
                :aria-label="field.label"
                :disabled="busy"
              />
            </label>
          </div>
          <template v-if="group.kind === 'image'">
            <p class="text-xs text-base-content/50">
              {{ config.cpuThreads }} CPU threads available. Save applies all four worker limits.
            </p>
            <div class="flex flex-wrap items-center justify-end gap-2">
              <button
                type="button"
                class="btn btn-ghost btn-xs"
                :disabled="busy"
                title="Detect recommended conversion and thumbnail workers"
                @click="detect"
              >
                <RefreshCw class="size-3.5" :class="{ 'animate-spin': detecting }" />
                {{ detecting ? "Detecting…" : "Auto detect" }}
              </button>
              <button
                type="submit"
                class="btn btn-primary btn-xs"
                :disabled="busy || !dirty || !valid"
              >
                {{ saving ? "Saving…" : "Save workers" }}
              </button>
            </div>
          </template>
        </div>
      </div>
    </template>
    <div v-if="error" class="flex flex-col items-start gap-2 px-4 py-3">
      <p role="alert" class="text-xs text-error">{{ error }}</p>
      <button v-if="!config && !loading" type="button" class="btn btn-ghost btn-xs" @click="load">
        Retry worker settings
      </button>
    </div>
  </form>
</template>
