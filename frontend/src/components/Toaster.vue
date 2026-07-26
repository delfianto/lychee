<script setup lang="ts">
import { AlertCircle, CheckCircle2, Info } from "lucide-vue-next";
import { computed } from "vue";

import { useToasts, type Toast } from "../lib/toast";

const toasts = useToasts();

const styleFor = computed(() => {
  return (type: Toast["type"]) => {
    switch (type) {
      case "error":
        return {
          box: "border-error/40 bg-base-100 text-base-content",
          icon: "text-error",
          Icon: AlertCircle,
        };
      case "info":
        return {
          box: "border-info/40 bg-base-100 text-base-content",
          icon: "text-info",
          Icon: Info,
        };
      default:
        return {
          box: "border-success/40 bg-base-100 text-base-content",
          icon: "text-success",
          Icon: CheckCircle2,
        };
    }
  };
});
</script>

<template>
  <!-- Sit just under the sticky navbar (h-14/16), right-aligned; above content, below modals. -->
  <div
    class="pointer-events-none fixed inset-x-0 top-14 z-30 flex flex-col items-end gap-2 px-3 pt-2 sm:top-16 sm:px-4"
    aria-live="polite"
  >
    <div
      v-for="t in toasts"
      :key="t.id"
      class="pointer-events-auto flex max-w-sm items-start gap-2.5 rounded-box border px-3.5 py-2.5 text-sm shadow-lg backdrop-blur-sm"
      :class="styleFor(t.type).box"
      role="status"
    >
      <component
        :is="styleFor(t.type).Icon"
        class="mt-0.5 size-4 shrink-0"
        :class="styleFor(t.type).icon"
        aria-hidden="true"
      />
      <span class="min-w-0 leading-snug text-base-content">{{ t.message }}</span>
    </div>
  </div>
</template>
