<script setup lang="ts">
import { RouterLink } from "vue-router";
defineProps<{ names: string[]; role: "author" | "artist" }>();
</script>

<template>
  <ul v-if="names.length" class="flex min-w-0 flex-col gap-1">
    <li v-for="name in names" :key="name" class="min-w-0">
      <RouterLink
        :to="{ path: '/search', query: { [role]: name } }"
        class="link link-hover wrap-anywhere"
        >{{ name }}</RouterLink
      >
    </li>
  </ul>
  <span v-else class="text-base-content/50">Not listed</span>
</template>
