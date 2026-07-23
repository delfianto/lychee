<script setup lang="ts">
import { computed, ref } from "vue";
import { RouterLink } from "vue-router";

import type { Series } from "../types";

const props = defineProps<{ items: Series[] }>();

const index = ref(0);
const current = computed(() => props.items[index.value]);

function go(step: number): void {
  const len = props.items.length;
  index.value = (index.value + step + len) % len;
}

function progress(s: Series | undefined): number {
  if (!s?.lastReadChapter || !s.totalChapters) return 0;
  return Math.round((s.lastReadChapter / s.totalChapters) * 100);
}
</script>

<template>
  <section v-if="current" class="relative overflow-hidden rounded-box bg-base-100">
    <div class="flex flex-col gap-4 p-4 sm:flex-row sm:gap-6 sm:p-6">
      <!-- Cover -->
      <img
        :src="current.coverUrl"
        :alt="current.title"
        class="cover w-32 shrink-0 rounded-box object-cover sm:w-44"
      />

      <!-- Info -->
      <div class="flex min-w-0 grow flex-col gap-3">
        <div>
          <h2 class="text-2xl font-bold">{{ current.title }}</h2>
          <p class="text-sm text-base-content/70">{{ current.authors.join(", ") }}</p>
        </div>

        <div class="flex flex-wrap gap-1">
          <span v-for="t in current.tags" :key="t.id" class="badge badge-sm badge-outline">
            {{ t.name }}
          </span>
        </div>

        <p class="line-clamp-2 text-sm text-base-content/70">{{ current.description }}</p>

        <div class="mt-auto flex flex-col gap-2">
          <div class="flex items-center gap-3">
            <progress
              class="progress progress-primary w-40"
              :value="progress(current)"
              max="100"
            ></progress>
            <span class="text-xs text-base-content/70">
              Ch. {{ current.lastReadChapter ?? 0 }} / {{ current.totalChapters ?? current.chapterCount }}
            </span>
          </div>
          <RouterLink :to="`/read/${current.id}`" class="btn btn-primary btn-sm w-fit">
            Continue reading
          </RouterLink>
        </div>
      </div>
    </div>

    <!-- Controls -->
    <button class="btn btn-circle btn-ghost btn-sm absolute left-2 top-1/2 -translate-y-1/2" @click="go(-1)">
      ‹
    </button>
    <button class="btn btn-circle btn-ghost btn-sm absolute right-2 top-1/2 -translate-y-1/2" @click="go(1)">
      ›
    </button>
    <div class="flex justify-center gap-1 pb-3">
      <button
        v-for="(_, i) in items"
        :key="i"
        class="h-2 w-2 rounded-full"
        :class="i === index ? 'bg-primary' : 'bg-base-300'"
        @click="index = i"
      ></button>
    </div>
  </section>
</template>
