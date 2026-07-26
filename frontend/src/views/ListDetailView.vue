<script setup lang="ts">
import { ArrowLeft, Pencil, Trash2 } from "lucide-vue-next";
import { ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";

import { fetchCollection } from "../api/queries";
import ConfirmDialog from "../components/ConfirmDialog.vue";
import SeriesCoverCard from "../components/SeriesCoverCard.vue";
import type { Series } from "../types";
import { useCollections } from "../stores/collections";

const route = useRoute();
const router = useRouter();
const collections = useCollections();

const listId = ref(String(route.params.id));
const name = ref("");
const works = ref<Series[]>([]);
const loading = ref(true);
const notFound = ref(false);

async function load(id: string): Promise<void> {
  listId.value = id;
  loading.value = true;
  notFound.value = false;
  const detail = await fetchCollection(id);
  if (detail === null) {
    notFound.value = true;
    works.value = [];
    name.value = "";
  } else {
    name.value = detail.name;
    works.value = detail.series;
  }
  loading.value = false;
}
watch(() => route.params.id, (id) => void load(String(id)), { immediate: true });

const editing = ref(false);
const editName = ref("");
function startRename(): void {
  editName.value = name.value;
  editing.value = true;
}
function saveRename(): void {
  if (editName.value.trim()) {
    void collections.renameList(listId.value, editName.value);
    name.value = editName.value.trim();
  }
  editing.value = false;
}
function removeWork(seriesId: string): void {
  void collections.removeSeries(listId.value, seriesId);
  works.value = works.value.filter((s) => s.id !== seriesId);
}
const deleteOpen = ref(false);
function del(): void {
  deleteOpen.value = true;
}
function confirmDeleteList(): void {
  deleteOpen.value = false;
  void collections.deleteList(listId.value);
  void router.push("/lists");
}
</script>

<template>
  <div class="flex flex-col gap-4 p-4 sm:p-6">
    <div v-if="notFound" class="py-16 text-center text-base-content/60">
      List not found. <RouterLink to="/lists" class="link">Back to lists</RouterLink>
    </div>
    <template v-else>
      <div class="flex flex-wrap items-center gap-3">
        <RouterLink to="/lists" class="btn btn-circle btn-ghost btn-sm" aria-label="Back to lists">
          <ArrowLeft class="size-5" />
        </RouterLink>
        <div class="grow">
          <div v-if="editing" class="flex items-center gap-2">
            <input v-model="editName" class="input input-bordered input-sm max-w-xs" @keyup.enter="saveRename" />
            <button class="btn btn-primary btn-sm" @click="saveRename">Save</button>
            <button class="btn btn-ghost btn-sm" @click="editing = false">Cancel</button>
          </div>
          <div v-else class="flex items-center gap-2">
            <h1 class="text-3xl font-bold">
              <span v-if="loading && !name" class="inline-block h-8 w-40 animate-pulse rounded bg-base-300" />
              <template v-else>{{ name }}</template>
            </h1>
            <button
              v-if="!loading"
              class="btn btn-circle btn-ghost btn-sm"
              aria-label="Rename list"
              @click="startRename"
            >
              <Pencil class="size-4" />
            </button>
          </div>
          <p class="text-sm text-base-content/60">
            <template v-if="loading">Loading…</template>
            <template v-else>{{ works.length }} works</template>
          </p>
        </div>
        <button v-if="!loading" class="btn btn-ghost btn-sm gap-1.5 text-error" @click="del">
          <Trash2 class="size-4" />Delete list
        </button>
      </div>

      <!-- Skeleton while the collection is in flight (never flash “No works yet”) -->
      <div
        v-if="loading"
        class="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6"
      >
        <div v-for="i in 6" :key="i" class="cover animate-pulse rounded-box bg-base-300" />
      </div>
      <div v-else-if="!works.length" class="py-16 text-center text-base-content/60">
        No works in this list yet. Add some from a series page.
      </div>
      <div
        v-else
        class="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6"
      >
        <SeriesCoverCard
          v-for="s in works"
          :key="s.id"
          :series="s"
          removable
          @remove="removeWork(s.id)"
        />
      </div>
    </template>

    <ConfirmDialog
      :open="deleteOpen"
      title="Delete list?"
      :message="`Delete the list “${name}”? This cannot be undone.`"
      confirm-label="Delete list"
      danger
      @confirm="confirmDeleteList"
      @cancel="deleteOpen = false"
    />
  </div>
</template>
