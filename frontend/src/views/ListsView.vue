<script setup lang="ts">
import { Layers, Plus, Trash2 } from "lucide-vue-next";
import { computed, ref } from "vue";
import { RouterLink } from "vue-router";

import { toast } from "../lib/toast";
import { useCollections } from "../stores/collections";
import type { Collection } from "../types";

defineOptions({ name: "ListsView" });

const collections = useCollections();
const creating = ref(false);
const newName = ref("");

// --- Kind tabs (mirrors LibraryView's shelf-status tabs) -----------------
type KindTab = "all" | "manga" | "comic" | "gallery";
const DEFAULT_TAB_KEY = "lychee.listsDefaultTab";
function initialTab(): KindTab {
  const stored = localStorage.getItem(DEFAULT_TAB_KEY);
  return stored === "manga" || stored === "comic" || stored === "gallery" || stored === "all"
    ? stored
    : "manga";
}
const kindTabs: { value: KindTab; label: string }[] = [
  { value: "all", label: "All" },
  { value: "manga", label: "Manga" },
  { value: "comic", label: "Comics" },
  { value: "gallery", label: "Gallery" },
];
const activeTab = ref<KindTab>(initialTab());

function matchesTab(list: Collection): boolean {
  return activeTab.value === "all" || list.kind === activeTab.value;
}
const visibleLists = computed(() => collections.lists.filter(matchesTab));
const activeTabLabel = computed(
  () => kindTabs.find((t) => t.value === activeTab.value)?.label ?? "",
);

async function create(): Promise<void> {
  const name = newName.value.trim();
  if (!name) return;
  await collections.createList(name);
  toast(`Created “${name}”`);
  newName.value = "";
  creating.value = false;
  // A brand-new list has no series yet, so it has no kind — jump to "All" so it
  // doesn't silently vanish from whichever kind tab was active.
  activeTab.value = "all";
}
function covers(seriesIds: string[]): string[] {
  return seriesIds.slice(0, 4).map((id) => `/api/series/${id}/cover`);
}
</script>

<template>
  <div class="flex flex-col gap-4 p-4 sm:p-6">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="text-3xl font-bold">Lists</h1>
        <p class="text-sm text-base-content/60">{{ visibleLists.length }} lists</p>
      </div>
      <button class="btn btn-primary btn-sm gap-1.5" @click="creating = !creating">
        <Plus class="size-4" />New list
      </button>
    </div>

    <!-- Kind tabs -->
    <div role="tablist" class="tabs tabs-box max-w-full self-start overflow-x-auto surface-border">
      <a
        v-for="tab in kindTabs"
        :key="tab.value"
        role="tab"
        class="tab whitespace-nowrap"
        :class="{ 'tab-active': activeTab === tab.value }"
        @click="activeTab = tab.value"
      >
        {{ tab.label }}
      </a>
    </div>

    <!-- Inline create -->
    <div v-if="creating" class="flex flex-wrap items-center gap-2 rounded-box surface-border bg-base-100 p-3">
      <input
        v-model="newName"
        type="text"
        placeholder="List name…"
        class="input input-bordered input-sm max-w-xs"
        @keyup.enter="create"
      />
      <button class="btn btn-primary btn-sm" :disabled="!newName.trim()" @click="create">Create</button>
      <button class="btn btn-ghost btn-sm" @click="creating = false">Cancel</button>
    </div>

    <div v-if="!collections.lists.length" class="py-16 text-center text-base-content/60">
      No lists yet — create one to group series together.
    </div>
    <div v-else-if="!visibleLists.length" class="py-16 text-center text-base-content/60">
      No {{ activeTab === "all" ? "" : `${activeTabLabel} ` }}lists yet.
    </div>

    <div v-else class="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
      <div v-for="l in visibleLists" :key="l.id" class="group relative">
        <RouterLink
          :to="`/lists/${l.id}`"
          class="block overflow-hidden rounded-box surface-border bg-base-100 transition hover:shadow-md"
        >
          <div class="grid aspect-video grid-cols-2 grid-rows-2 gap-0.5 bg-base-300">
            <img v-for="(c, i) in covers(l.seriesIds)" :key="i" :src="c" alt="" class="h-full w-full object-cover" />
            <div
              v-if="!l.seriesIds.length"
              class="col-span-2 row-span-2 flex items-center justify-center text-base-content/30"
            >
              <Layers class="size-8" />
            </div>
          </div>
          <div class="p-3">
            <h3 class="truncate font-semibold">{{ l.name }}</h3>
            <p class="text-xs text-base-content/60">{{ l.seriesIds.length }} works</p>
          </div>
        </RouterLink>
        <button
          class="btn btn-circle btn-error btn-xs absolute right-2 top-2 opacity-0 transition group-hover:opacity-100"
          aria-label="Delete list"
          @click="collections.deleteList(l.id)"
        >
          <Trash2 class="size-3.5" />
        </button>
      </div>
    </div>
  </div>
</template>
