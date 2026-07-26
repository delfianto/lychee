<script setup lang="ts">
// Labeled server path input + Browse button that opens the shared PathBrowserModal.
// Used by Add Library and Local Import so both pick paths the same way.
import { FolderSearch } from "lucide-vue-next";
import { ref } from "vue";

import PathBrowserModal from "./PathBrowserModal.vue";

const props = withDefaults(
  defineProps<{
    modelValue: string;
    label?: string;
    placeholder?: string;
    disabled?: boolean;
    /** Allow selecting a file in the browser (import); default directories only. */
    allowFiles?: boolean;
    browserTitle?: string;
  }>(),
  {
    label: "Path",
    placeholder: "/data/manga",
    disabled: false,
    allowFiles: false,
    browserTitle: "Browse storage",
  },
);

const emit = defineEmits<{
  "update:modelValue": [value: string];
  /** Fired only when the user picks via the storage browser (not free-typing). */
  pick: [value: string];
}>();

const showBrowser = ref(false);

function onPicked(path: string): void {
  emit("update:modelValue", path);
  emit("pick", path);
  showBrowser.value = false;
}
</script>

<template>
  <div class="flex flex-col gap-1">
    <label v-if="label" class="text-xs text-base-content/60">{{ label }}</label>
    <div class="flex gap-2">
      <input
        :value="modelValue"
        type="text"
        class="input input-bordered input-sm min-w-0 flex-1 font-mono"
        :placeholder="placeholder"
        :disabled="disabled"
        @input="emit('update:modelValue', ($event.target as HTMLInputElement).value)"
      />
      <button
        type="button"
        class="btn btn-ghost btn-sm w-28 shrink-0 gap-1 surface-border"
        title="Browse the server storage directory"
        :disabled="disabled"
        @click="showBrowser = true"
      >
        <FolderSearch class="size-4" />Browse
      </button>
    </div>
  </div>

  <PathBrowserModal
    v-if="showBrowser"
    :initial-path="modelValue"
    :allow-files="allowFiles"
    :title="browserTitle"
    @close="showBrowser = false"
    @select="onPicked"
  />
</template>
