<script setup lang="ts">
// Navbar affordance for background work (scans, downloads). Hidden when idle;
// while tasks run it shows a spinning badge that opens a live progress list,
// fed by the shared SSE task stream.
import { Loader2, Square } from "@lucide/vue";
import { RouterLink } from "vue-router";

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

function closeDropdown(): void {
  if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
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
      class="dropdown-content z-30 mt-2 max-h-96 w-72 overflow-y-auto rounded-box border border-base-300 bg-base-100 p-3 shadow-lg max-sm:fixed max-sm:inset-x-2 max-sm:top-16 max-sm:w-auto"
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
            <div class="flex items-center gap-2">
              <RouterLink
                class="link link-hover"
                :to="{
                  path: '/settings',
                  query: { section: task.kind === 'download' ? 'downloads' : 'sync' },
                }"
                @click="closeDropdown"
                >View {{ task.kind === "download" ? "downloads" : "sync" }}</RouterLink
              >
              <button
                class="btn btn-ghost btn-xs"
                :disabled="task.status === 'cancelling'"
                :aria-label="`Cancel ${task.label}`"
                @click="cancelTask(task.id)"
              >
                <Square class="size-3" /> Cancel
              </button>
            </div>
          </div>
          <PhaseProgress :phases="task.phases ?? {}" />
          <div class="mt-1.5 text-xs">
            <div class="flex justify-between gap-3 text-base-content/60">
              <span class="min-w-0 truncate">{{ task.detail ?? "Overall" }}</span>
              <span class="shrink-0 tabular-nums">{{ task.progress }}%</span>
            </div>
            <progress
              class="progress progress-primary h-1 w-full"
              aria-label="Overall progress"
              :value="task.progress"
              max="100"
            />
          </div>
        </li>
      </ul>
    </div>
  </div>
</template>
