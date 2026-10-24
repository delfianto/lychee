<script setup lang="ts">
import { computed } from "vue";

import { parseMangaDescription } from "../lib/description";

const props = withDefaults(
  defineProps<{
    text?: string | null;
    /** When true, limit a long synopsis preview to seven lines. */
    clamp?: boolean;
    /** Show the Namespace/Tags table (detail pages). */
    showTagTable?: boolean;
  }>(),
  { clamp: false, showTagTable: true },
);

const parsed = computed(() => parseMangaDescription(props.text));
</script>

<template>
  <div v-if="parsed.synopsis || parsed.tagGroups.length" class="flex min-w-0 flex-col gap-3">
    <!-- Markdown prose and general tables; source HTML is disabled. -->
    <div
      v-if="parsed.synopsis"
      class="series-desc wrap-anywhere text-sm leading-relaxed text-base-content/80"
      :class="{ 'line-clamp-7': clamp }"
      v-html="parsed.synopsisHtml"
    />

    <!-- Namespace tag table — structured, not pipe soup -->
    <div
      v-for="(section, sectionIndex) in showTagTable ? parsed.tagSections : []"
      :key="sectionIndex"
      class="min-w-0 overflow-hidden rounded-box border border-base-300"
    >
      <h3
        v-if="section.label"
        class="border-b border-base-300 bg-base-200/60 px-3 py-2 text-sm font-semibold"
      >
        {{ section.label }}
      </h3>
      <div class="overflow-x-auto">
        <table class="table table-sm w-full table-fixed">
          <thead>
            <tr class="bg-base-200/60 text-xs uppercase tracking-wide text-base-content/60">
              <th class="w-28">Namespace</th>
              <th>Tags</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(g, groupIndex) in section.groups" :key="groupIndex">
              <td class="wrap-anywhere align-top font-semibold uppercase text-base-content/70">
                {{ g.namespace }}
              </td>
              <td>
                <div class="flex flex-wrap gap-1">
                  <span
                    v-for="(tag, tagIndex) in g.tags"
                    :key="tagIndex"
                    class="badge badge-ghost badge-sm h-auto max-w-full whitespace-normal wrap-anywhere font-normal"
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
  </div>
</template>
