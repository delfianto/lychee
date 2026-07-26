<script setup lang="ts">
import { X } from "lucide-vue-next";
import { nextTick, onMounted, onUnmounted, ref, watch } from "vue";

const props = withDefaults(
  defineProps<{
    open: boolean;
    title: string;
    label?: string;
    placeholder?: string;
    confirmLabel?: string;
    cancelLabel?: string;
    busy?: boolean;
  }>(),
  {
    label: "",
    placeholder: "",
    confirmLabel: "Create",
    cancelLabel: "Cancel",
    busy: false,
  },
);

const emit = defineEmits<{ submit: [value: string]; cancel: [] }>();

const value = ref("");
const inputEl = ref<HTMLInputElement | null>(null);

watch(
  () => props.open,
  async (open) => {
    document.body.classList.toggle("overflow-hidden", open);
    if (open) {
      value.value = "";
      await nextTick();
      inputEl.value?.focus();
    }
  },
);

function onKey(e: KeyboardEvent): void {
  if (!props.open) return;
  if (e.key === "Escape") emit("cancel");
}

function submit(): void {
  const v = value.value.trim();
  if (!v || props.busy) return;
  emit("submit", v);
}

onMounted(() => window.addEventListener("keydown", onKey));
onUnmounted(() => {
  window.removeEventListener("keydown", onKey);
  document.body.classList.remove("overflow-hidden");
});
</script>

<template>
  <div v-if="open" class="modal modal-open" role="dialog" aria-modal="true" @click.self="emit('cancel')">
    <div class="modal-box max-w-md">
      <div class="mb-3 flex items-start justify-between gap-3">
        <h3 class="text-lg font-bold">{{ title }}</h3>
        <button
          type="button"
          class="btn btn-circle btn-ghost btn-sm shrink-0"
          aria-label="Close"
          :disabled="busy"
          @click="emit('cancel')"
        >
          <X class="size-4" />
        </button>
      </div>
      <label v-if="label" class="mb-1 block text-sm text-base-content/70">{{ label }}</label>
      <input
        ref="inputEl"
        v-model="value"
        type="text"
        class="input input-bordered w-full"
        :placeholder="placeholder"
        :disabled="busy"
        @keyup.enter="submit"
      />
      <div class="modal-action">
        <button type="button" class="btn btn-ghost" :disabled="busy" @click="emit('cancel')">
          {{ cancelLabel }}
        </button>
        <button
          type="button"
          class="btn btn-primary"
          :disabled="busy || !value.trim()"
          @click="submit"
        >
          <span v-if="busy" class="loading loading-spinner loading-sm" />
          {{ confirmLabel }}
        </button>
      </div>
    </div>
  </div>
</template>
