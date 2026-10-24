<script setup lang="ts">
import { Check, Minus, Search, X } from "@lucide/vue";
import { computed, ref } from "vue";
import CreatorInput from "./CreatorInput.vue";
import FilterDropdown from "./FilterDropdown.vue";
import FilterSelect from "./FilterSelect.vue";
import type { TagGroup } from "../api/queries";
import { demographicLabel, ratingLabel } from "../lib/ratingLabels";
import type { BrowseFilters, ContentRating, Demographic, PublicationStatus } from "../types";

const props = withDefaults(
  defineProps<{
    filters: BrowseFilters;
    tagGroups?: TagGroup[];
    sort?: string;
    sortOptions?: string[];
  }>(),
  {
    tagGroups: () => [],
    sort: "Recently Added",
    sortOptions: () => ["Rating", "Recently Added", "Recently Updated", "Title", "Unread"],
  },
);
const emit = defineEmits<{
  "update:sort": [value: string];
  "set-author": [value: string];
  "set-artist": [value: string];
  "set-tag-mode": [mode: "and" | "or"];
  "toggle-tag": [id: string];
  "toggle-rating": [value: ContentRating];
  "toggle-demographic": [value: Demographic];
  "toggle-status": [value: PublicationStatus];
  "toggle-read-state": [value: string];
}>();
const ratingOptions = (
  ["safe", "suggestive", "erotica", "pornographic", "explicit"] as ContentRating[]
).map((value) => ({ value, label: ratingLabel(value) }));
const demographicOptions = (["shonen", "shojo", "seinen", "josei"] as Demographic[]).map(
  (value) => ({ value, label: demographicLabel(value) }),
);
const statusOptions = ["ongoing", "completed", "hiatus", "cancelled"].map((value) => ({
  value,
  label: value.charAt(0).toUpperCase() + value.slice(1),
}));
const readStateOptions = [
  { value: "unread", label: "Unread" },
  { value: "in_progress", label: "In progress" },
  { value: "read", label: "Read" },
];
const tagQuery = ref("");
const visibleGroups = computed(() =>
  props.tagGroups
    .map((group) => ({
      ...group,
      tags: group.tags.filter((tag) =>
        tag.name.toLocaleLowerCase().includes(tagQuery.value.trim().toLocaleLowerCase()),
      ),
    }))
    .filter((group) => group.tags.length),
);
const tagCount = computed(() => Object.keys(props.filters.tags).length);
const tagSummary = computed(() => {
  const selected = Object.entries(props.filters.tags);
  if (!selected.length) return "Any";
  if (selected.length === 1) {
    const [id, state] = selected[0]!;
    const name =
      props.tagGroups.flatMap((group) => group.tags).find((tag) => tag.id === id)?.name ?? id;
    return `${state === "include" ? "Include" : "Exclude"} ${name}`;
  }
  const included = selected.filter(([, state]) => state === "include").length;
  return `${included} included · ${selected.length - included} excluded`;
});
function clearTags(): void {
  // The parent owns the neutral → include → exclude → neutral cycle.
  for (const [id, state] of Object.entries(props.filters.tags)) {
    if (state === "include") emit("toggle-tag", id);
    emit("toggle-tag", id);
  }
}
</script>

<template>
  <div class="grid grid-cols-1 gap-x-6 gap-y-5 sm:grid-cols-2 lg:grid-cols-4">
    <label class="flex min-w-0 flex-col gap-1.5 text-sm">
      <span class="text-base-content/65">Sort by</span>
      <select
        class="select h-10 w-full bg-base-200"
        :value="sort"
        aria-label="Sort by"
        @change="emit('update:sort', ($event.target as HTMLSelectElement).value)"
      >
        <option v-for="option in sortOptions" :key="option">{{ option }}</option>
      </select>
    </label>
    <FilterDropdown label="Filter tags" :summary="tagSummary" :count="tagCount">
      <div class="relative mb-2">
        <Search
          class="pointer-events-none absolute top-1/2 left-3 z-10 size-3.5 -translate-y-1/2 text-base-content/50"
        />
        <input
          v-model="tagQuery"
          type="search"
          placeholder="Find tags…"
          aria-label="Find tags"
          class="input input-sm w-full bg-base-200 pl-9"
        />
      </div>
      <div class="mb-2 flex items-center justify-between gap-2 border-b border-base-300 pb-2">
        <div class="join" role="group" aria-label="Match included tags">
          <button
            v-for="mode in ['and', 'or'] as const"
            :key="mode"
            type="button"
            class="btn join-item btn-xs"
            :class="{ 'btn-active': filters.tagMode === mode }"
            :aria-pressed="filters.tagMode === mode"
            @click="emit('set-tag-mode', mode)"
          >
            {{ mode.toUpperCase() }}
          </button>
        </div>
        <button type="button" class="btn btn-ghost btn-xs" :disabled="!tagCount" @click="clearTags">
          <X class="size-3" />Clear tags
        </button>
      </div>
      <p class="mb-2 px-1 text-xs text-base-content/60">Click to include, again to exclude.</p>
      <div class="max-h-64 overflow-y-auto overscroll-contain">
        <div v-for="group in visibleGroups" :key="group.group" class="mb-2 last:mb-0">
          <div class="px-2 py-1 text-xs font-semibold text-base-content/60">{{ group.group }}</div>
          <button
            v-for="tag in group.tags"
            :key="tag.id"
            type="button"
            class="flex w-full items-center gap-2 rounded-field px-2 py-2 text-left text-sm hover:bg-base-200"
            :aria-label="`${tag.name}: ${filters.tags[tag.id] ?? 'any'}`"
            @click="emit('toggle-tag', tag.id)"
          >
            <span
              class="flex size-4 shrink-0 items-center justify-center rounded-sm border border-base-content/30"
              :class="{
                'border-success text-success': filters.tags[tag.id] === 'include',
                'border-error text-error': filters.tags[tag.id] === 'exclude',
              }"
              ><Check v-if="filters.tags[tag.id] === 'include'" class="size-3" /><Minus
                v-else-if="filters.tags[tag.id] === 'exclude'"
                class="size-3"
            /></span>
            <span class="grow">{{ tag.name }}</span>
            <span
              v-if="filters.tags[tag.id]"
              class="text-xs capitalize"
              :class="filters.tags[tag.id] === 'include' ? 'text-success' : 'text-error'"
              >{{ filters.tags[tag.id] }}</span
            >
          </button>
        </div>
        <p v-if="!visibleGroups.length" class="px-2 py-4 text-sm text-base-content/60">
          No matching tags.
        </p>
      </div>
    </FilterDropdown>
    <FilterSelect
      label="Content rating"
      :options="ratingOptions"
      :selected="filters.ratings"
      @toggle="emit('toggle-rating', $event as ContentRating)"
    />
    <FilterSelect
      label="Magazine demographic"
      :options="demographicOptions"
      :selected="filters.demographics"
      @toggle="emit('toggle-demographic', $event as Demographic)"
    />
    <CreatorInput
      role="author"
      :model-value="filters.author ?? ''"
      @update:model-value="emit('set-author', $event)"
    />
    <CreatorInput
      role="artist"
      :model-value="filters.artist ?? ''"
      @update:model-value="emit('set-artist', $event)"
    />
    <FilterSelect
      label="Publication status"
      :options="statusOptions"
      :selected="filters.statuses"
      @toggle="emit('toggle-status', $event as PublicationStatus)"
    />
    <FilterSelect
      label="Read status"
      :options="readStateOptions"
      :selected="filters.readStates"
      @toggle="emit('toggle-read-state', $event)"
    />
  </div>
</template>
