<script setup lang="ts">
import { ArrowLeft, Pencil, Pin, Trash2 } from "@lucide/vue";
import { ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";

import { fetchCollection } from "../api/queries";
import ConfirmDialog from "../components/ConfirmDialog.vue";
import SeriesCoverCard from "../components/SeriesCoverCard.vue";
import MangaDexListActions from "../components/MangaDexListActions.vue";
import { mediaKindLabel } from "../lib/display";
import { toast } from "../lib/toast";
import type { Series, Collection } from "../types";
import { useCollections } from "../stores/collections";
import { useHome } from "../stores/home";

const route = useRoute();
const router = useRouter();
const collections = useCollections();
const home = useHome();

const listId = ref(String(route.params.id));
const name = ref("");
const works = ref<Series[]>([]);
const metadata = ref<Collection | null>(null);
const busy = ref(false);
const remoteDelete = ref(false);
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
    metadata.value = detail;
    name.value = detail.name;
    works.value = detail.series;
  }
  loading.value = false;
}
watch(
  () => route.params.id,
  (id) => void load(String(id)),
  { immediate: true },
);

const editing = ref(false);
const editName = ref("");
function startRename(): void {
  editName.value = name.value;
  editing.value = true;
}
async function saveRename(): Promise<void> {
  if (!editName.value.trim()) {
    editing.value = false;
    return;
  }
  busy.value = true;
  try {
    await collections.renameList(listId.value, editName.value);
    name.value = editName.value.trim();
    editing.value = false;
  } catch (e) {
    toast(e instanceof Error ? e.message : "Couldn't rename list", "error");
  } finally {
    busy.value = false;
  }
}
async function removeWork(seriesId: string): Promise<void> {
  try {
    await collections.removeSeries(listId.value, seriesId);
    works.value = works.value.filter((s) => s.id !== seriesId);
  } catch (e) {
    toast(e instanceof Error ? e.message : "Couldn't remove from list", "error");
  }
}
async function changed(): Promise<void> {
  await collections.refresh();
  await load(listId.value);
}
const deleteOpen = ref(false);
function del(remote = false): void {
  remoteDelete.value = remote;
  deleteOpen.value = true;
}
async function confirmDeleteList(): Promise<void> {
  busy.value = true;
  try {
    await collections.deleteList(listId.value, remoteDelete.value);
    deleteOpen.value = false;
    await router.push("/lists");
  } catch (e) {
    toast(e instanceof Error ? e.message : "Couldn't delete list", "error");
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <div class="flex flex-col gap-4 p-4 sm:p-6" :data-browse-loading="loading || undefined">
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
            <input
              v-model="editName"
              class="input input-bordered input-sm max-w-xs"
              @keyup.enter="saveRename"
            />
            <button class="btn btn-primary btn-sm" @click="saveRename">Save</button>
            <button class="btn btn-ghost btn-sm" @click="editing = false">Cancel</button>
          </div>
          <div v-else class="flex items-center gap-2">
            <h1 class="text-3xl font-bold">
              <span
                v-if="loading && !name"
                class="inline-block h-8 w-40 animate-pulse rounded bg-base-300"
              />
              <template v-else>{{ name }}</template>
            </h1>
            <button
              v-if="!loading && metadata?.editable !== false"
              class="btn btn-circle btn-ghost btn-sm"
              aria-label="Rename list"
              @click="startRename"
            >
              <Pencil class="size-4" />
            </button>
          </div>
          <p class="text-sm text-base-content/60">
            <template v-if="loading">Loading…</template>
            <template v-else
              ><span class="badge badge-ghost badge-sm mr-2">{{
                mediaKindLabel[metadata?.kind ?? "manga"]
              }}</span
              >{{ works.length }} works</template
            >
          </p>
        </div>
        <button
          v-if="!loading"
          class="btn btn-ghost btn-sm gap-1.5"
          :aria-pressed="home.preferences.pins.some((pin) => pin.id === `list:${listId}`)"
          @click="home.pin({ id: `list:${listId}`, type: 'list', collectionId: listId })"
        >
          <Pin class="size-4" />{{
            home.preferences.pins.some((pin) => pin.id === `list:${listId}`)
              ? "Pinned to Home"
              : "Show on Home"
          }}
        </button>
        <button v-if="!loading" class="btn btn-ghost btn-sm gap-1.5 text-error" @click="del(false)">
          <Trash2 class="size-4" />{{ metadata?.provider ? "Remove from Lychee" : "Delete list" }}
        </button>
      </div>

      <MangaDexListActions
        v-if="!loading && metadata?.provider === 'mangadex'"
        :key="listId"
        :collection="metadata"
        @changed="changed"
      />
      <button
        v-if="!loading && metadata?.owned"
        class="btn btn-ghost btn-sm self-start text-error"
        @click="del(true)"
      >
        Delete from MangaDex
      </button>
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
          :removable="metadata?.editable !== false"
          @remove="removeWork(s.id)"
        />
      </div>
    </template>

    <ConfirmDialog
      :open="deleteOpen"
      :title="
        remoteDelete
          ? 'Delete from MangaDex?'
          : metadata?.provider
            ? 'Remove from Lychee?'
            : 'Delete list?'
      "
      :message="
        remoteDelete
          ? `Permanently delete “${name}” on MangaDex and remove its local list? Manga files are kept.`
          : metadata?.provider
            ? 'Remove this local copy only? The MangaDex list is kept and may return on account sync.'
            : `Delete the list “${name}”? This cannot be undone.`
      "
      :confirm-label="
        remoteDelete
          ? 'Delete from MangaDex'
          : metadata?.provider
            ? 'Remove from Lychee'
            : 'Delete list'
      "
      :busy="busy"
      danger
      @confirm="confirmDeleteList"
      @cancel="deleteOpen = false"
    />
  </div>
</template>
