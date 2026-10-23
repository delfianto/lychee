<script setup lang="ts">
// Navbar affordance for background work (scans, downloads). Hidden when idle;
// while tasks run it shows a spinning badge that opens a live progress list,
// fed by the shared SSE task stream.
import { Loader2, Square } from "@lucide/vue";

import { activeTasks } from "../api/events";
import { api } from "../api/client";
import { toast } from "../lib/toast";
import PhaseProgress from "./PhaseProgress.vue";

async function cancelTask(id: string): Promise<void> {
  const { error } = await api.POST("/api/tasks/{task_id}/cancel", {
    params: { path: { task_id: id } },
  });
  if (error) toast("Couldn't cancel operation", "error");
}

function kindLabel(kind: string): string {
  if (kind === "thumbs") return "Thumbs";
  if (kind === "scan") return "Scan";
  if (kind === "download") return "DL";
  if (kind === "metadata") return "Meta";
  return kind;
}
</script>

<template>
  <div v-if="activeTasks.length" class="dropdown dropdown-end">
    <div
      tabindex="0"
      role="button"
      class="btn btn-circle btn-ghost btn-sm"
      :aria-label="`${activeTasks.length} background task(s) running`"
    >
      <span class="indicator">
        <span class="indicator-item badge badge-primary badge-xs">{{ activeTasks.length }}</span>
        <Loader2 class="size-5 animate-spin text-primary" />
      </span>
    </div>
    <div
      tabindex="0"
      class="dropdown-content z-30 mt-2 w-72 rounded-box border border-base-300 bg-base-100 p-3 shadow-lg"
    >
      <p class="mb-2 text-xs font-semibold uppercase tracking-wide opacity-60">Background tasks</p>
      <ul class="space-y-3">
        <li v-for="task in activeTasks" :key="task.id">
          <div class="flex justify-between gap-2 text-sm">
            <span class="min-w-0 truncate">
              <span class="badge badge-ghost badge-xs mr-1 align-middle">{{
                kindLabel(task.kind)
              }}</span>
              {{ task.label }}
            </span>
            <span class="shrink-0 tabular-nums opacity-60">{{ task.progress }}%</span>
          </div>
          <div class="mt-1 flex items-center justify-between gap-2 text-xs">
            <span class="capitalize">{{ task.status }}</span>
            <button
              class="btn btn-ghost btn-xs"
              :disabled="task.status === 'cancelling'"
              :aria-label="`Cancel ${task.label}`"
              @click="cancelTask(task.id)"
            >
              <Square class="size-3" /> Cancel
            </button>
          </div>
          <PhaseProgress :phases="task.phases ?? {}" />
          <progress
            class="progress progress-primary mt-1 h-1.5 w-full"
            :value="task.progress"
            max="100"
          />
          <p v-if="task.detail" class="truncate text-xs opacity-50">{{ task.detail }}</p>
        </li>
      </ul>
    </div>
  </div>
</template>
