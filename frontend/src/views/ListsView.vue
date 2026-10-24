<script setup lang="ts">
import { Plus, Trash2 } from "@lucide/vue";
import { computed, ref, watch } from "vue";
import { RouterLink } from "vue-router";

import { type ListsTab, useListsDefaultTab } from "../lib/density";
import CollectionCover from "../components/CollectionCover.vue";
import { mediaKindLabel } from "../lib/display";
import { toast } from "../lib/toast";
import { useCollections } from "../stores/collections";
import MangaDexListImport from "../components/MangaDexListImport.vue";
import type { Collection } from "../types";

defineOptions({ name: "ListsView" });

const collections = useCollections();
const creating = ref(false);
const newName = ref("");
const location = ref("local");
const visibility = ref<"public" | "private">("private");
const busy = ref(false);
const newKind = ref<"manga" | "comic" | "gallery">("manga");
watch(location, (value) => {
  if (value === "mangadex") newKind.value = "manga";
});
function toggleCreate(): void {
  if (!creating.value) newKind.value = activeTab.value === "all" ? "manga" : activeTab.value;
  creating.value = !creating.value;
}

// --- Kind tabs (mirrors LibraryView's shelf-status tabs) -----------------
const { listsDefaultTab } = useListsDefaultTab();
const kindTabs: { value: ListsTab; label: string }[] = [
  { value: "all", label: "All" },
  { value: "manga", label: "Manga" },
  { value: "comic", label: "Comics" },
  { value: "gallery", label: "Gallery" },
];
// Seeded from (and kept live with) the shared default, but the page's own tab
// clicks are session-local and don't write back to it — only Settings does.
const activeTab = ref<ListsTab>(listsDefaultTab.value);
watch(listsDefaultTab, (t) => {
  activeTab.value = t;
});

function matchesTab(list: Collection): boolean {
  return activeTab.value === "all" || list.kind === activeTab.value;
}
const visibleLists = computed(() =>
  collections.lists
    .filter(matchesTab)
    .sort((a, b) =>
      a.name.localeCompare(b.name, undefined, { sensitivity: "base", numeric: true }),
    ),
);
const activeTabLabel = computed(
  () => kindTabs.find((t) => t.value === activeTab.value)?.label ?? "",
);

async function create(): Promise<void> {
  const name = newName.value.trim();
  if (!name) return;
  busy.value = true;
  try {
    await collections.createList(name, {
      kind: newKind.value,
      ...(location.value === "mangadex"
        ? { provider: "mangadex" as const, visibility: visibility.value }
        : {}),
    });
    toast(`Created “${name}”`);
    newName.value = "";
    creating.value = false;
    activeTab.value = newKind.value;
  } catch (e) {
    toast(e instanceof Error ? e.message : "Couldn't create list", "error");
  } finally {
    busy.value = false;
  }
}
async function removeList(id: string) {
  try {
    await collections.deleteList(id);
  } catch (e) {
    toast(e instanceof Error ? e.message : "Couldn't delete list", "error");
  }
}
</script>

<template>
  <div class="flex flex-col gap-4 p-4 sm:p-6">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="text-3xl font-bold">Lists</h1>
        <p class="text-sm text-base-content/60">{{ visibleLists.length }} lists</p>
      </div>
      <button class="btn btn-primary btn-sm gap-1.5" @click="toggleCreate">
        <Plus class="size-4" />New list
      </button>
    </div>

    <MangaDexListImport />
    <!-- Kind tabs -->
    <div role="tablist" class="tabs tabs-box max-w-full self-start overflow-x-auto surface-border">
      <button
        v-for="tab in kindTabs"
        :key="tab.value"
        type="button"
        role="tab"
        class="tab whitespace-nowrap"
        :class="{ 'tab-active': activeTab === tab.value }"
        @click="activeTab = tab.value"
      >
        {{ tab.label }}
      </button>
    </div>

    <!-- Inline create -->
    <div
      v-if="creating"
      class="flex flex-wrap items-center gap-2 rounded-box surface-border bg-base-100 p-3"
    >
      <input
        v-model="newName"
        type="text"
        placeholder="List name…"
        class="input input-bordered input-sm max-w-xs"
        @keyup.enter="create"
      />
      <select
        v-model="newKind"
        aria-label="List type"
        class="select select-bordered select-sm"
        :disabled="location === 'mangadex'"
      >
        <option value="manga">Manga</option>
        <option value="comic">Comic</option>
        <option value="gallery">Gallery</option>
      </select>
      <select
        v-model="location"
        class="select select-bordered select-sm"
        aria-label="List location"
      >
        <option value="local">Local list</option>
        <option value="mangadex">MangaDex list</option>
      </select>
      <select
        v-if="location === 'mangadex'"
        v-model="visibility"
        class="select select-bordered select-sm"
        aria-label="New list visibility"
      >
        <option value="private">Private</option>
        <option value="public">Public</option>
      </select>
      <button class="btn btn-primary btn-sm" :disabled="busy || !newName.trim()" @click="create">
        Create
      </button>
      <button class="btn btn-ghost btn-sm" @click="creating = false">Cancel</button>
    </div>

    <div v-if="!collections.lists.length" class="py-16 text-center text-base-content/60">
      No lists yet — create one to group series together.
    </div>
    <div v-else-if="!visibleLists.length" class="py-16 text-center text-base-content/60">
      No {{ activeTab === "all" ? "" : `${activeTabLabel} ` }}lists yet.
    </div>

    <div
      v-else
      class="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:gallery-columns"
    >
      <div v-for="l in visibleLists" :key="l.id" class="group relative">
        <RouterLink
          :to="`/lists/${l.id}`"
          class="block overflow-hidden rounded-box surface-border bg-base-100 transition hover:shadow-md"
        >
          <CollectionCover :series-ids="l.seriesIds" />
          <div class="p-3">
            <h3 class="truncate font-semibold">{{ l.name }}</h3>
            <span class="badge badge-ghost badge-xs">{{ mediaKindLabel[l.kind ?? "manga"] }}</span>
            <span v-if="l.provider === 'mangadex'" class="badge badge-outline badge-xs"
              >MangaDex · {{ l.owned ? "Owned" : l.followed ? "Followed" : "Imported" }} ·
              {{ l.visibility }}</span
            >
            <p class="text-xs text-base-content/60">{{ l.seriesIds.length }} works</p>
          </div>
        </RouterLink>
        <button
          v-if="!l.provider"
          class="btn btn-circle btn-error btn-xs absolute right-2 top-2 opacity-0 transition group-hover:opacity-100"
          aria-label="Delete list"
          @click="removeList(l.id)"
        >
          <Trash2 class="size-3.5" />
        </button>
      </div>
    </div>
  </div>
</template>
