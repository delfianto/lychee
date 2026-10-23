<script setup lang="ts">
import { X } from "@lucide/vue";
import { computed, nextTick, onMounted, onUnmounted, ref, useId, watch } from "vue";

import { parseMangaDescription } from "../lib/description";
import SeriesDescription from "./SeriesDescription.vue";

const props = defineProps<{ text: string; title: string }>();
const headingId = useId();
const preview = ref<HTMLElement | null>(null);
const dialog = ref<HTMLDialogElement | null>(null);
const clipped = ref(false);
const parsed = computed(() => parseMangaDescription(props.text));
// Ordinary multi-paragraph blurbs should be readable without opening a dialog.
// Only substantial descriptions need the bounded seven-line preview.
const longSynopsis = computed(() => parsed.value.synopsis.length > 1200);
const hasTags = computed(() => parsed.value.tagGroups.length > 0);
let observer: ResizeObserver | undefined;

function measure(): void {
  const synopsis = preview.value?.querySelector<HTMLElement>(".series-desc");
  clipped.value =
    longSynopsis.value && !!synopsis && synopsis.scrollHeight > synopsis.clientHeight + 1;
}

onMounted(() => {
  observer = new ResizeObserver(measure);
  if (preview.value) observer.observe(preview.value);
  measure();
});
onUnmounted(() => observer?.disconnect());
watch(
  () => props.text,
  async () => {
    dialog.value?.close();
    await nextTick();
    measure();
  },
);
</script>

<template>
  <div>
    <div ref="preview">
      <SeriesDescription :text="text" :clamp="longSynopsis" :show-tag-table="false" />
    </div>
    <button
      v-if="clipped || hasTags"
      class="btn btn-ghost btn-xs mt-2"
      aria-haspopup="dialog"
      @click="dialog?.showModal()"
    >
      Read full description
    </button>

    <!-- Native modal keeps the page inert, traps focus, handles Escape, and
         restores focus to the trigger. Only its reading area scrolls. -->
    <dialog ref="dialog" class="modal" :aria-labelledby="headingId" @click.self="dialog?.close()">
      <div class="modal-box flex max-w-3xl flex-col overflow-hidden p-0">
        <header
          class="flex shrink-0 items-start justify-between gap-4 border-b border-base-300 p-5"
        >
          <div class="min-w-0">
            <h2 :id="headingId" class="text-lg font-semibold">Description</h2>
            <p class="mt-1 wrap-anywhere text-sm text-base-content/60">{{ title }}</p>
          </div>
          <button
            type="button"
            class="btn btn-circle btn-ghost btn-sm shrink-0"
            aria-label="Close description"
            autofocus
            @click="dialog?.close()"
          >
            <X class="size-4" />
          </button>
        </header>
        <div class="min-h-0 overflow-y-auto overscroll-contain p-5">
          <SeriesDescription :text="text" />
        </div>
      </div>
    </dialog>
  </div>
</template>
