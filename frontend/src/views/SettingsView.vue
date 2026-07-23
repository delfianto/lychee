<script setup lang="ts">
import { computed, reactive, ref } from "vue";

import { browseTagGroups } from "../mocks/library";
import type { ContentRating } from "../types";

const sections = [
  { key: "libraries", label: "Libraries" },
  { key: "tags", label: "Tags" },
  { key: "rating", label: "Content Rating" },
  { key: "providers", label: "Metadata & Providers" },
  { key: "trackers", label: "Trackers" },
  { key: "reader", label: "Reader" },
  { key: "appearance", label: "Appearance" },
  { key: "about", label: "About" },
];
const active = ref("tags");
const activeLabel = computed(() => sections.find((s) => s.key === active.value)?.label ?? "");

// Mock tag management state (per-tag enabled flag + usage count).
const enabled = reactive<Record<string, boolean>>({});
const usage = reactive<Record<string, number>>({});
browseTagGroups.forEach((g) =>
  g.tags.forEach((t, i) => {
    enabled[t.id] = true;
    usage[t.id] = (i + 2) * 13;
  }),
);

// Mock content ratings (top tier is "Mature").
const ratings = reactive<{ key: ContentRating; label: string; level: number; enabled: boolean }[]>([
  { key: "safe", label: "Safe", level: 0, enabled: true },
  { key: "suggestive", label: "Suggestive", level: 1, enabled: true },
  { key: "erotica", label: "Erotica", level: 2, enabled: true },
  { key: "mature", label: "Mature", level: 3, enabled: true },
]);
const levelWidths = ["w-1/4", "w-1/2", "w-3/4", "w-full"];
const levelWidth = (level: number): string => levelWidths[level] ?? "w-full";
</script>

<template>
  <div class="flex flex-col gap-6 p-4 sm:p-6">
    <!-- Section tabs (horizontal) -->
    <div role="tablist" class="tabs tabs-border overflow-x-auto">
      <a
        v-for="s in sections"
        :key="s.key"
        role="tab"
        class="tab whitespace-nowrap"
        :class="{ 'tab-active': active === s.key }"
        @click="active = s.key"
      >
        {{ s.label }}
      </a>
    </div>

    <!-- Panel -->
    <div class="min-w-0">
      <!-- Tags -->
      <div v-if="active === 'tags'" class="flex flex-col gap-4">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <h2 class="text-lg font-semibold">Tags</h2>
          <div class="flex items-center gap-2">
            <label class="input input-bordered input-sm flex items-center gap-2">
              <span class="opacity-60">⌕</span>
              <input type="search" class="grow" placeholder="Search tags…" />
            </label>
            <button class="btn btn-primary btn-sm">+ Add tag</button>
          </div>
        </div>

        <div v-for="g in browseTagGroups" :key="g.group" class="card bg-base-100">
          <div class="card-body gap-2 p-4">
            <h3 class="text-sm font-semibold text-base-content/70">{{ g.group }}</h3>
            <div class="overflow-x-auto">
              <table class="table table-sm">
                <tbody>
                  <tr v-for="t in g.tags" :key="t.id">
                    <td class="w-6 cursor-grab text-base-content/40">⠿</td>
                    <td class="font-medium">{{ t.name }}</td>
                    <td><span class="badge badge-ghost badge-sm">default</span></td>
                    <td class="text-xs text-base-content/60">{{ usage[t.id] }} uses</td>
                    <td>
                      <input v-model="enabled[t.id]" type="checkbox" class="toggle toggle-primary toggle-sm" />
                    </td>
                    <td class="text-right">
                      <button class="btn btn-ghost btn-xs">Edit</button>
                      <button class="btn btn-ghost btn-xs text-error" disabled>Delete</button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>

      <!-- Content rating -->
      <div v-else-if="active === 'rating'" class="flex flex-col gap-4">
        <h2 class="text-lg font-semibold">Content Rating</h2>
        <div class="card bg-base-100">
          <div class="card-body gap-4 p-4">
            <div v-for="r in ratings" :key="r.key" class="flex items-center gap-4">
              <span class="w-24 shrink-0 font-medium">{{ r.label }}</span>
              <div class="h-2 grow overflow-hidden rounded-full bg-base-300">
                <div class="h-2 rounded-full bg-primary" :class="levelWidth(r.level)"></div>
              </div>
              <span class="w-16 shrink-0 text-right text-xs text-base-content/60">level {{ r.level }}</span>
              <input v-model="r.enabled" type="checkbox" class="toggle toggle-primary toggle-sm" />
            </div>
          </div>
        </div>
        <p class="text-xs text-base-content/60">
          Higher level = more explicit. Drives per-library content filtering.
        </p>
      </div>

      <!-- Other sections (stubs) -->
      <div v-else class="flex flex-col gap-3">
        <h2 class="text-lg font-semibold">{{ activeLabel }}</h2>
        <div class="card bg-base-100">
          <div class="card-body p-4 text-sm text-base-content/60">This section is coming soon.</div>
        </div>
      </div>
    </div>
  </div>
</template>
