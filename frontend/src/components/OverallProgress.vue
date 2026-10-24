<script setup lang="ts">
defineProps<{ progress: number }>();
</script>

<template>
  <div class="mt-1.5 text-xs">
    <div class="flex justify-between gap-3 text-base-content/60">
      <span>Overall progress</span>
      <span class="shrink-0 tabular-nums">{{ progress }}%</span>
    </div>
    <progress
      class="progress progress-primary h-1 w-full"
      aria-label="Overall progress"
      :value="progress"
      max="100"
    />
  </div>
</template>
