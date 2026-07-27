<script setup lang="ts">
// Search MangaDex for a metadata match and link the series to it. Runs an initial
// search on open (seeded from the series title); emits `matched` once linked so the
// parent can reload metadata.
import { X } from "lucide-vue-next";
import { ref } from "vue";

import { fetchMatchCandidates, matchSeries, type MatchCandidate } from "../api/queries";
import { useFocusTrap } from "../lib/focusTrap";

const props = defineProps<{ seriesId: string; initialQuery: string }>();
const emit = defineEmits<{ close: []; matched: [] }>();

// No `open` prop — the parent mounts this component only while shown.
const modalBox = ref<HTMLElement | null>(null);
useFocusTrap(modalBox, ref(true));

const query = ref(props.initialQuery);
const loading = ref(false);
const results = ref<MatchCandidate[]>([]);

async function search(): Promise<void> {
  loading.value = true;
  results.value = await fetchMatchCandidates(props.seriesId, query.value.trim() || undefined);
  loading.value = false;
}
async function pick(c: MatchCandidate): Promise<void> {
  await matchSeries(props.seriesId, c.providerSeriesId);
  emit("matched");
}

void search();
</script>

<template>
  <div class="modal modal-open" @click.self="emit('close')">
    <div ref="modalBox" class="modal-box max-w-2xl">
      <div class="mb-3 flex items-center justify-between">
        <h3 class="text-lg font-bold">Match on MangaDex</h3>
        <button class="btn btn-circle btn-ghost btn-sm" aria-label="Close" @click="emit('close')">
          <X class="size-4" />
        </button>
      </div>
      <label class="input input-bordered flex items-center gap-2">
        <input v-model="query" class="grow" placeholder="Search title…" aria-label="Search for a matching series" @keyup.enter="search" />
        <button class="btn btn-primary btn-sm" @click="search">Search</button>
      </label>
      <div v-if="loading" class="flex justify-center py-8">
        <span class="loading loading-spinner text-primary" />
      </div>
      <ul v-else class="mt-4 max-h-96 space-y-2 overflow-y-auto">
        <li v-for="c in results" :key="c.providerSeriesId">
          <button
            class="flex w-full items-center gap-3 rounded-lg p-2 text-left hover:bg-base-200"
            @click="pick(c)"
          >
            <img v-if="c.coverUrl" :src="c.coverUrl" :alt="c.title" class="h-16 w-12 shrink-0 rounded object-cover" />
            <div v-else class="h-16 w-12 shrink-0 rounded bg-base-300" />
            <div class="min-w-0">
              <div class="truncate font-medium">{{ c.title }}</div>
              <div class="text-xs text-base-content/60">
                {{ [c.year, c.status].filter(Boolean).join(" · ") || "—" }}
              </div>
            </div>
          </button>
        </li>
        <li v-if="!results.length" class="py-8 text-center text-sm text-base-content/50">
          No matches found
        </li>
      </ul>
    </div>
  </div>
</template>
