<script setup lang="ts">
import { RouterLink } from "vue-router";
</script>

<template>
  <div class="flex flex-col items-center justify-center gap-4 py-24 text-center">
    <div class="text-7xl font-bold text-base-content/20">404</div>
    <h1 class="text-xl font-semibold">Page not found</h1>
    <p class="text-sm text-base-content/60">That page doesn’t exist or has moved.</p>
    <RouterLink to="/" class="btn btn-primary btn-sm">Back to home</RouterLink>
  </div>
</template>
