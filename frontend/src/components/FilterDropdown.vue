<script setup lang="ts">
import { ChevronsUpDown } from "@lucide/vue";
import { onBeforeUnmount, onMounted, ref, useId } from "vue";

defineProps<{ label: string; summary: string; count?: number }>();
const id = useId();
const details = ref<HTMLDetailsElement | null>(null);
function close(event: PointerEvent): void {
  if (event.target instanceof Node && !details.value?.contains(event.target))
    details.value?.removeAttribute("open");
}
function escape(): void {
  details.value?.removeAttribute("open");
  details.value?.querySelector("summary")?.focus();
}
onMounted(() => document.addEventListener("pointerdown", close));
onBeforeUnmount(() => document.removeEventListener("pointerdown", close));
</script>

<template>
  <div class="flex min-w-0 flex-col gap-1.5">
    <span class="text-sm text-base-content/65">
      {{ label
      }}<span v-if="count" class="ml-2 text-xs font-medium text-primary">+{{ count }}</span>
    </span>
    <details
      ref="details"
      name="library-filter"
      class="dropdown w-full"
      @keydown.esc.stop.prevent="escape"
    >
      <summary
        class="flex h-10 w-full cursor-pointer list-none items-center justify-between gap-2 rounded-field bg-base-200 px-3 text-sm surface-border focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        :aria-label="label"
        :aria-describedby="id"
      >
        <span :id="id" class="truncate">{{ summary }}</span>
        <ChevronsUpDown class="size-4 shrink-0 text-base-content/50" />
      </summary>
      <div
        class="dropdown-content z-30 mt-2 w-full rounded-box bg-base-100 p-2 shadow-xl surface-border"
      >
        <slot />
      </div>
    </details>
  </div>
</template>
