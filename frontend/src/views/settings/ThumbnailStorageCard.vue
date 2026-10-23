<script setup lang="ts">
import { HardDrive } from "@lucide/vue";
import { computed, onMounted, ref } from "vue";
import { fetchThumbnailStorage, saveThumbnailStorage } from "../../api/settingsQueries";
import ServerPathField from "../../components/ServerPathField.vue";
import { toast } from "../../lib/toast";

const mode = ref("default");
const path = ref("");
const defaultPath = ref("");
const savedPath = ref<string | null>(null);
const loading = ref(true);
const saving = ref(false);
const error = ref("");
const ready = ref(false);
const dirty = computed(
  () => (mode.value === "custom" ? path.value.trim() : null) !== savedPath.value,
);

async function load(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const config = await fetchThumbnailStorage();
    defaultPath.value = config.defaultPath;
    savedPath.value = config.path;
    path.value = config.path ?? "";
    mode.value = config.path === null ? "default" : "custom";
    ready.value = true;
  } catch (err) {
    error.value = (err as Error).message;
  } finally {
    loading.value = false;
  }
}

async function save(): Promise<void> {
  saving.value = true;
  error.value = "";
  try {
    const config = await saveThumbnailStorage(mode.value === "custom" ? path.value.trim() : null);
    savedPath.value = config.path;
    path.value = config.path ?? "";
    toast("Thumbnail storage saved");
  } catch (err) {
    error.value = (err as Error).message;
  } finally {
    saving.value = false;
  }
}
onMounted(load);
</script>

<template>
  <form class="flex flex-col gap-2 border-b border-base-content/10 pb-4" @submit.prevent="save">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <div class="flex items-start gap-3">
        <HardDrive class="mt-0.5 size-5 shrink-0 text-primary" />
        <div>
          <h3 class="text-sm font-medium">Thumbnail storage</h3>
          <p class="text-xs text-base-content/50">Cover and gallery thumbnails for all libraries</p>
        </div>
      </div>
      <select
        v-if="ready"
        v-model="mode"
        aria-label="Thumbnail storage location"
        class="select select-bordered select-sm w-32 shrink-0"
        :disabled="saving"
      >
        <option value="default">Default folder</option>
        <option value="custom">Custom folder</option>
      </select>
    </div>
    <p v-if="loading" class="text-xs text-base-content/60" role="status">
      Loading storage settings…
    </p>
    <template v-if="ready">
      <ServerPathField
        v-if="mode === 'custom'"
        v-model="path"
        label="Thumbnail folder (absolute path on the server)"
        placeholder="/data/thumbnails"
        browser-title="Choose thumbnail folder"
        :disabled="saving"
      />
      <p v-else class="break-all font-mono text-xs text-base-content/50">{{ defaultPath }}</p>
      <p v-if="dirty" class="text-xs text-base-content/50">
        Existing thumbnails stay in place; missing ones regenerate here.
      </p>
    </template>
    <p v-if="error" class="text-xs text-error" role="alert">{{ error }}</p>
    <button
      v-if="!ready && !loading"
      type="button"
      class="btn btn-ghost btn-xs self-start"
      @click="load"
    >
      Retry
    </button>
    <button
      v-if="ready && dirty"
      class="btn btn-primary btn-xs self-end"
      :disabled="saving || (mode === 'custom' && !path.trim())"
    >
      {{ saving ? "Saving…" : "Save thumbnail storage" }}
    </button>
  </form>
</template>
