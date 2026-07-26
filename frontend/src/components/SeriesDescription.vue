<script setup lang="ts">
import { computed } from "vue";

import { parseMangaDescription } from "../lib/description";

const props = withDefaults(
  defineProps<{
    text?: string | null;
    /** When true, clamp the synopsis to a few lines. */
    clamp?: boolean;
    /** Show the Namespace/Tags table (detail pages). */
    showTagTable?: boolean;
  }>(),
  { clamp: false, showTagTable: true },
);

const parsed = computed(() => parseMangaDescription(props.text));
</script>

<template>
  <div v-if="parsed.synopsis || parsed.tagGroups.length" class="flex flex-col gap-3">
    <!-- Synopsis: light Markdown (escaped) -->
    <div
      v-if="parsed.synopsis"
      class="series-desc text-sm text-base-content/80"
      :class="{ 'line-clamp-3': clamp }"
      v-html="parsed.synopsisHtml"
    />

    <!-- Namespace tag table — structured, not pipe soup -->
    <div v-if="showTagTable && parsed.tagGroups.length" class="overflow-x-auto rounded-box border border-base-300">
      <table class="table table-sm">
        <thead>
          <tr class="bg-base-200/60 text-xs uppercase tracking-wide text-base-content/60">
            <th class="w-28">Namespace</th>
            <th>Tags</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="g in parsed.tagGroups" :key="g.namespace">
            <td class="align-top font-semibold uppercase text-base-content/70">{{ g.namespace }}</td>
            <td>
              <div class="flex flex-wrap gap-1">
                <span
                  v-for="tag in g.tags"
                  :key="tag"
                  class="badge badge-ghost badge-sm font-normal"
                >
                  {{ tag }}
                </span>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
