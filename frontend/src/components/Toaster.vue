<script setup lang="ts">
import { useToasts } from "../lib/toast";

const toasts = useToasts();
</script>

<template>
  <div class="toast toast-end toast-bottom z-50">
    <div
      v-for="t in toasts"
      :key="t.id"
      class="alert py-2 text-sm shadow-lg"
      :class="{
        'alert-success': t.type === 'success',
        'alert-error': t.type === 'error',
        'alert-info': t.type === 'info',
      }"
    >
      <span>{{ t.message }}</span>
    </div>
  </div>
</template>
