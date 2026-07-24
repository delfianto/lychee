<script setup lang="ts">
import { ArrowLeft, Pencil, Trash2 } from "lucide-vue-next";
import { computed, ref } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";

import SeriesCoverCard from "../components/SeriesCoverCard.vue";
import { findSeries } from "../mocks/library";
import { useCollections } from "../stores/collections";

const route = useRoute();
const router = useRouter();
const collections = useCollections();

const list = computed(() => collections.getList(String(route.params.id)));
const works = computed(() => (list.value ? list.value.seriesIds.map((id) => findSeries(id)) : []));

const editing = ref(false);
const editName = ref("");
function startRename(): void {
  if (list.value) {
    editName.value = list.value.name;
    editing.value = true;
  }
}
function saveRename(): void {
  if (list.value) collections.renameList(list.value.id, editName.value);
  editing.value = false;
}
function removeWork(seriesId: string): void {
  if (list.value) collections.removeSeries(list.value.id, seriesId);
}
function del(): void {
  if (list.value && confirm(`Delete the list “${list.value.name}”?`)) {
    collections.deleteList(list.value.id);
    void router.push("/lists");
  }
}
</script>

<template>
  <div class="flex flex-col gap-4 p-4 sm:p-6">
    <div v-if="!list" class="py-16 text-center text-base-content/60">
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
            <h1 class="text-3xl font-bold">{{ list?.name }}</h1>
            <button class="btn btn-circle btn-ghost btn-sm" aria-label="Rename list" @click="startRename">
              <Pencil class="size-4" />
            </button>
          </div>
          <p class="text-sm text-base-content/60">{{ works.length }} works</p>
        </div>
        <button class="btn btn-ghost btn-sm gap-1.5 text-error" @click="del">
          <Trash2 class="size-4" />Delete list
        </button>
      </div>

      <div v-if="!works.length" class="py-16 text-center text-base-content/60">
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
  </div>
</template>
