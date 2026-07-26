<script setup lang="ts">
import { X } from "lucide-vue-next";
import { onMounted, onUnmounted, watch } from "vue";

const props = withDefaults(
  defineProps<{
    open: boolean;
    title: string;
    message?: string;
    confirmLabel?: string;
    cancelLabel?: string;
    /** Error-styled confirm for destructive actions. */
    danger?: boolean;
    busy?: boolean;
  }>(),
  {
    message: "",
    confirmLabel: "Confirm",
    cancelLabel: "Cancel",
    danger: false,
    busy: false,
  },
);

const emit = defineEmits<{ confirm: []; cancel: [] }>();

function onKey(e: KeyboardEvent): void {
  if (!props.open) return;
  if (e.key === "Escape") emit("cancel");
}

watch(
  () => props.open,
  (open) => {
    document.body.classList.toggle("overflow-hidden", open);
  },
);

onMounted(() => window.addEventListener("keydown", onKey));
onUnmounted(() => {
  window.removeEventListener("keydown", onKey);
  document.body.classList.remove("overflow-hidden");
});
</script>

<template>
  <div v-if="open" class="modal modal-open" role="alertdialog" aria-modal="true" @click.self="emit('cancel')">
    <div class="modal-box max-w-md">
      <div class="mb-3 flex items-start justify-between gap-3">
        <h3 class="text-lg font-bold leading-snug">{{ title }}</h3>
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
      <p v-if="message" class="whitespace-pre-line text-sm text-base-content/80">{{ message }}</p>
      <slot />
      <div class="modal-action">
        <button type="button" class="btn btn-ghost" :disabled="busy" @click="emit('cancel')">
          {{ cancelLabel }}
        </button>
        <button
          type="button"
          class="btn"
          :class="danger ? 'btn-error' : 'btn-primary'"
          :disabled="busy"
          @click="emit('confirm')"
        >
          <span v-if="busy" class="loading loading-spinner loading-sm" />
          {{ confirmLabel }}
        </button>
      </div>
    </div>
  </div>
</template>
