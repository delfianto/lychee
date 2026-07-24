<script setup lang="ts">
import { browseTagGroups } from "../mocks/library";
import type { BrowseFilters, ContentRating, Demographic, PublicationStatus } from "../types";

const props = defineProps<{ filters: BrowseFilters }>();

const ratingOptions: ContentRating[] = ["safe", "suggestive", "erotica", "mature"];
const demographicOptions: Demographic[] = ["shonen", "shojo", "seinen", "josei"];
const statusOptions: PublicationStatus[] = ["ongoing", "completed", "hiatus", "cancelled"];
const readStateOptions: { value: string; label: string }[] = [
  { value: "unread", label: "Unread" },
  { value: "in_progress", label: "In progress" },
  { value: "read", label: "Read" },
];

// Cycle a tag chip: neutral → include → exclude → neutral.
function cycleTag(id: string): void {
  const cur = props.filters.tags[id];
  if (!cur) props.filters.tags[id] = "include";
  else if (cur === "include") props.filters.tags[id] = "exclude";
  else delete props.filters.tags[id];
}
function tagClass(id: string): string {
  const s = props.filters.tags[id];
  return s === "include" ? "btn-success" : s === "exclude" ? "btn-error" : "btn-ghost";
}
function toggle<T>(set: Set<T>, value: T): void {
  if (set.has(value)) set.delete(value);
  else set.add(value);
}
</script>

<template>
  <div class="flex flex-col gap-4">
    <!-- Tags (tri-state include/exclude + AND/OR) -->
    <div class="flex flex-col gap-2">
      <div class="flex items-center gap-2">
        <span class="text-sm font-semibold">Tags</span>
        <div class="join ml-auto">
          <button class="btn join-item btn-xs" :class="{ 'btn-active': filters.tagMode === 'and' }" @click="filters.tagMode = 'and'">AND</button>
          <button class="btn join-item btn-xs" :class="{ 'btn-active': filters.tagMode === 'or' }" @click="filters.tagMode = 'or'">OR</button>
        </div>
      </div>
      <div v-for="g in browseTagGroups" :key="g.group" class="flex flex-col gap-1">
        <span class="text-xs text-base-content/60">{{ g.group }}</span>
        <div class="flex flex-wrap gap-1">
          <button v-for="t in g.tags" :key="t.id" class="btn btn-xs" :class="tagClass(t.id)" @click="cycleTag(t.id)">
            {{ t.name }}
          </button>
        </div>
      </div>
    </div>

    <!-- Facets -->
    <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <div class="flex flex-col gap-2">
        <span class="text-sm font-semibold">Content rating</span>
        <div class="flex flex-wrap gap-1">
          <button v-for="r in ratingOptions" :key="r" class="btn btn-xs capitalize" :class="filters.ratings.has(r) ? 'btn-primary' : 'btn-ghost'" @click="toggle(filters.ratings, r)">
            {{ r }}
          </button>
        </div>
      </div>
      <div class="flex flex-col gap-2">
        <span class="text-sm font-semibold">Demographic</span>
        <div class="flex flex-wrap gap-1">
          <button v-for="d in demographicOptions" :key="d" class="btn btn-xs capitalize" :class="filters.demographics.has(d) ? 'btn-primary' : 'btn-ghost'" @click="toggle(filters.demographics, d)">
            {{ d }}
          </button>
        </div>
      </div>
      <div class="flex flex-col gap-2">
        <span class="text-sm font-semibold">Publication status</span>
        <div class="flex flex-wrap gap-1">
          <button v-for="s in statusOptions" :key="s" class="btn btn-xs capitalize" :class="filters.statuses.has(s) ? 'btn-primary' : 'btn-ghost'" @click="toggle(filters.statuses, s)">
            {{ s }}
          </button>
        </div>
      </div>
      <div class="flex flex-col gap-2">
        <span class="text-sm font-semibold">Read status</span>
        <div class="flex flex-wrap gap-1">
          <button v-for="rs in readStateOptions" :key="rs.value" class="btn btn-xs" :class="filters.readStates.has(rs.value) ? 'btn-primary' : 'btn-ghost'" @click="toggle(filters.readStates, rs.value)">
            {{ rs.label }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
