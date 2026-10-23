<script setup lang="ts">
import { computed } from "vue";
import type { ChapterAvailability } from "../api/queries";
const props = defineProps<{ availability: ChapterAvailability; checking?: boolean }>();
defineEmits<{ retry: [] }>();
const message = computed(() => {
  switch (props.availability.status) {
    case "error":
      return (
        props.availability.message ??
        "Could not check chapters on MangaDex. This does not mean the manga has no chapters."
      );
    case "language_unavailable":
      return `No readable chapters in ${props.availability.language.toUpperCase()}. Chapters are available in other languages: ${props.availability.availableLanguages.join(", ").toUpperCase()}. Choose another language above.`;
    case "unavailable":
      return "MangaDex has chapter records for this title, but none are currently readable. They may have been removed or made unavailable; MangaDex does not provide the reason here.";
    case "external_only":
      return "Chapters in this language link to an external publisher and cannot be downloaded by Lychee. Open MangaDex to follow those links.";
    case "no_chapters":
      return "MangaDex currently reports no chapters for this title in any language. The chapter check completed successfully.";
    case "ready":
      return "No chapters match this view. Check the selected language or refresh the chapter list.";
    case "local":
      return "No chapters in the library for this series.";
    default:
      return "Chapter availability has not been checked yet.";
  }
});
</script>
<template>
  <div
    class="flex flex-col items-center gap-3 py-8 text-center text-sm text-base-content/60"
    :role="availability.status === 'error' ? 'alert' : 'status'"
  >
    <p class="max-w-prose">{{ message }}</p>
    <p v-if="availability.checkedAt" class="text-xs">
      Last checked {{ new Date(availability.checkedAt).toLocaleString() }}
    </p>
    <div v-if="availability.status !== 'local'" class="flex flex-wrap justify-center gap-2">
      <button class="btn btn-ghost btn-sm" :disabled="checking" @click="$emit('retry')">
        {{
          checking
            ? "Checking chapters…"
            : availability.status === "error"
              ? "Retry chapter check"
              : "Check again"
        }}
      </button>
      <a
        v-if="availability.sourceUrl"
        :href="availability.sourceUrl"
        target="_blank"
        rel="noopener noreferrer"
        class="btn btn-ghost btn-sm"
        >Open on MangaDex</a
      >
    </div>
  </div>
</template>
