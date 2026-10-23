<script setup lang="ts">
const props = defineProps<{
  phases: Record<string, Record<string, number>>;
}>();

const labels: Record<string, string> = {
  fetching: "Download",
  encoding: "Convert",
  thumbnails: "Thumbnails",
  covers: "Covers",
  inspect: "Inspect files",
  index: "Index",
  metadata: "Metadata",
  account: "Account",
  lists: "Lists",
  ratings: "Ratings",
  reading: "Reading progress",
  chapters: "Chapter index",
};
</script>

<template>
  <div class="mt-2 space-y-1.5" aria-label="Operation phases">
    <div v-for="(counts, name) in props.phases" :key="name" class="text-xs">
      <div class="flex justify-between gap-3 text-base-content/60">
        <span>{{ labels[name] ?? name }}</span>
        <span class="tabular-nums">{{ counts.completed ?? 0 }}/{{ counts.total ?? 0 }}</span>
      </div>
      <progress
        class="progress progress-primary h-1 w-full"
        :aria-label="labels[name] ?? name"
        :value="counts.total ? Math.min(counts.completed ?? 0, counts.total) : undefined"
        :max="counts.total || 1"
      />
    </div>
  </div>
</template>
