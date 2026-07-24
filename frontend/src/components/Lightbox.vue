<script setup lang="ts">
import { ChevronLeft, ChevronRight, X } from "lucide-vue-next";
import { onBeforeUnmount, onMounted } from "vue";

// Full-screen image viewer for galleries: prev/next, keyboard (←/→/Esc), counter.
const props = defineProps<{ images: string[]; index: number }>();
const emit = defineEmits<{ close: []; "update:index": [number] }>();

function go(delta: number): void {
  const n = props.images.length;
  emit("update:index", (props.index + delta + n) % n);
}
function onKey(e: KeyboardEvent): void {
  if (e.key === "Escape") emit("close");
  else if (e.key === "ArrowLeft") go(-1);
  else if (e.key === "ArrowRight") go(1);
}
onMounted(() => window.addEventListener("keydown", onKey));
onBeforeUnmount(() => window.removeEventListener("keydown", onKey));
</script>

<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/90 p-4" @click.self="emit('close')">
    <button class="btn btn-circle btn-ghost absolute right-3 top-3 text-white" aria-label="Close" @click="emit('close')">
      <X class="size-6" />
    </button>
    <button
      class="btn btn-circle btn-ghost absolute left-3 top-1/2 -translate-y-1/2 text-white"
      aria-label="Previous image"
      @click="go(-1)"
    >
      <ChevronLeft class="size-7" />
    </button>
    <img :src="images[index]" alt="" class="max-h-[90vh] max-w-[90vw] rounded object-contain shadow-2xl" />
    <button
      class="btn btn-circle btn-ghost absolute right-3 top-1/2 -translate-y-1/2 text-white"
      aria-label="Next image"
      @click="go(1)"
    >
      <ChevronRight class="size-7" />
    </button>
    <div class="absolute bottom-4 left-1/2 -translate-x-1/2 rounded-full bg-black/50 px-3 py-1 text-xs text-white/80">
      {{ index + 1 }} / {{ images.length }}
    </div>
  </div>
</template>
