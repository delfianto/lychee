<script setup lang="ts">
import { Cpu } from "@lucide/vue";
import { computed, onMounted, ref } from "vue";
import { fetchImageProcessing, saveImageProcessing } from "../../api/settingsQueries";
import { toast } from "../../lib/toast";

const config = ref<Awaited<ReturnType<typeof fetchImageProcessing>> | null>(null);
const conversion = ref(1);
const thumbnails = ref(1);
const loading = ref(true);
const saving = ref(false);
const error = ref("");
const valid = computed(() =>
  [conversion.value, thumbnails.value].every(
    (value) => Number.isInteger(value) && value >= 1 && value <= 64,
  ),
);
const dirty = computed(
  () =>
    !!config.value &&
    (conversion.value !== config.value.conversionWorkers ||
      thumbnails.value !== config.value.thumbnailWorkers),
);
function setConfig(next: Awaited<ReturnType<typeof fetchImageProcessing>>): void {
  config.value = next;
  conversion.value = next.conversionWorkers;
  thumbnails.value = next.thumbnailWorkers;
}
async function load(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    setConfig(await fetchImageProcessing());
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Could not load image processing settings";
  } finally {
    loading.value = false;
  }
}
function recommend(): void {
  if (!config.value) return;
  conversion.value = config.value.recommendedConversionWorkers;
  thumbnails.value = config.value.recommendedThumbnailWorkers;
}
async function save(): Promise<void> {
  if (!valid.value || saving.value) return;
  saving.value = true;
  error.value = "";
  try {
    setConfig(await saveImageProcessing(conversion.value, thumbnails.value));
    toast("Image processing settings saved");
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Could not save image processing settings";
  } finally {
    saving.value = false;
  }
}
onMounted(load);
</script>

<template>
  <form class="settings-row" @submit.prevent="save">
    <div class="flex items-start gap-3">
      <Cpu class="mt-0.5 size-5 shrink-0 text-primary" />
      <div>
        <h4 class="text-sm font-medium">Image processing</h4>
        <p class="mt-1 text-xs text-base-content/50">
          Separate limits for conversion and thumbnail workers
        </p>
      </div>
    </div>
    <div class="flex min-w-0 flex-col gap-3 xl:col-span-2">
      <p v-if="loading" class="text-xs text-base-content/60" role="status">
        Loading worker settings…
      </p>
      <template v-if="config">
        <div class="grid gap-3 sm:grid-cols-2">
          <label
            class="flex min-w-0 items-center justify-between gap-3 rounded-md bg-base-200/50 px-3 py-2"
          >
            <span class="min-w-0 text-xs">
              <span class="block font-medium">Conversion workers</span>
              <span class="mt-0.5 block text-base-content/50">Pages and imports</span>
            </span>
            <input
              v-model.number="conversion"
              type="number"
              min="1"
              max="64"
              step="1"
              class="input input-bordered input-sm w-20 shrink-0"
              aria-label="Conversion workers"
              :disabled="saving"
            />
          </label>
          <label
            class="flex min-w-0 items-center justify-between gap-3 rounded-md bg-base-200/50 px-3 py-2"
          >
            <span class="min-w-0 text-xs">
              <span class="block font-medium">Thumbnail workers</span>
              <span class="mt-0.5 block text-base-content/50">Covers and gallery previews</span>
            </span>
            <input
              v-model.number="thumbnails"
              type="number"
              min="1"
              max="64"
              step="1"
              class="input input-bordered input-sm w-20 shrink-0"
              aria-label="Thumbnail workers"
              :disabled="saving"
            />
          </label>
        </div>
        <p class="text-xs text-base-content/50">
          {{ config.cpuThreads }} CPU threads available. Changes apply immediately; download
          concurrency is separate.
        </p>
        <div class="flex flex-wrap items-center justify-between gap-2">
          <button type="button" class="btn btn-ghost btn-xs" :disabled="saving" @click="recommend">
            Use recommended ({{ config.recommendedConversionWorkers }} /
            {{ config.recommendedThumbnailWorkers }})
          </button>
          <button
            type="submit"
            class="btn btn-primary btn-xs"
            :disabled="saving || !dirty || !valid"
          >
            {{ saving ? "Saving…" : "Save image processing" }}
          </button>
        </div>
      </template>
      <p v-if="error" role="alert" class="text-xs text-error">{{ error }}</p>
      <button
        v-if="!config && !loading"
        type="button"
        class="btn btn-ghost btn-xs self-start"
        @click="load"
      >
        Retry worker settings
      </button>
    </div>
  </form>
</template>
