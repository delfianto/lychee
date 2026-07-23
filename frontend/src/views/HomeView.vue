<script setup lang="ts">
import { onMounted, ref } from "vue";

// Bare skeleton: ping the backend so we can see the two halves are wired together.
const status = ref("…");

onMounted(async () => {
  try {
    const res = await fetch("/api/health");
    const data = (await res.json()) as { status: string };
    status.value = data.status;
  } catch {
    status.value = "unreachable";
  }
});
</script>

<template>
  <!-- DaisyUI component classes + canonical Tailwind utilities only (no raw/arbitrary values). -->
  <div class="min-h-screen bg-base-200">
    <div class="navbar bg-base-100 shadow-sm">
      <div class="flex-1">
        <span class="btn btn-ghost text-xl">🍒 lychee</span>
      </div>
    </div>

    <div class="hero py-16">
      <div class="hero-content text-center">
        <div class="max-w-md">
          <h1 class="text-4xl font-bold">lychee</h1>
          <p class="py-4 text-base-content/70">Self-hosted manga / comic / ebook media server.</p>
          <div class="flex items-center justify-center gap-2">
            <span>backend</span>
            <span class="badge" :class="status === 'ok' ? 'badge-success' : 'badge-warning'">
              {{ status }}
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
