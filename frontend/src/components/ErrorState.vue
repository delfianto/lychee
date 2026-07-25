<script setup lang="ts">
// Shared load-failure UI: a message + a Retry button. Used where a view would
// otherwise sit on an infinite spinner (or a misleading empty state) when an API
// call fails.
import { AlertTriangle } from "lucide-vue-next";

defineProps<{ message?: string }>();
defineEmits<{ retry: [] }>();
</script>

<template>
  <div class="flex flex-col items-center gap-3 py-20 text-center">
    <AlertTriangle class="size-8 text-error/70" />
    <p class="max-w-sm text-sm text-base-content/70">{{ message ?? "Something went wrong while loading." }}</p>
    <button class="btn btn-sm btn-outline gap-1" @click="$emit('retry')">Try again</button>
  </div>
</template>
