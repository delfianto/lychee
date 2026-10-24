<script setup lang="ts">
import { ChevronDown, Clock, GalleryThumbnails, HardDrive, Images, Layers } from "@lucide/vue";
import { computed, onMounted, ref } from "vue";
import { fetchThumbnailStorage, saveThumbnailStorage } from "../../api/settingsQueries";
import ImageProcessingSettings from "./ImageProcessingSettings.vue";
import ServerPathField from "../../components/ServerPathField.vue";
import { RECENTLY_ADDED_OPTIONS, useMainBarIcons, useRecentlyAddedKinds } from "../../lib/density";
import { toast } from "../../lib/toast";

const { recentlyAddedKinds, toggleRecentlyAddedKind } = useRecentlyAddedKinds();
const { mainBarIcons } = useMainBarIcons();
const selectedKindsLabel = computed(() => {
  const labels = RECENTLY_ADDED_OPTIONS.filter((opt) =>
    recentlyAddedKinds.value.includes(opt.value),
  ).map((opt) => opt.label);
  return labels.length ? labels.join(", ") : "None";
});

const path = ref("");
const defaultPath = ref("");
const savedPath = ref<string | null>(null);
const loading = ref(true);
const saving = ref(false);
const error = ref("");
const ready = ref(false);
const selectedPath = computed(() => {
  const value = path.value.trim();
  return value === defaultPath.value ? null : value;
});
const usingDefault = computed(() => selectedPath.value === null);
const dirty = computed(() => selectedPath.value !== savedPath.value);

async function load(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const config = await fetchThumbnailStorage();
    defaultPath.value = config.defaultPath;
    savedPath.value = config.path;
    path.value = config.effectivePath;
    ready.value = true;
  } catch (err) {
    error.value = (err as Error).message;
  } finally {
    loading.value = false;
  }
}

async function save(): Promise<void> {
  if (!ready.value || saving.value || !dirty.value || !path.value.trim()) return;
  saving.value = true;
  error.value = "";
  try {
    const config = await saveThumbnailStorage(selectedPath.value);
    savedPath.value = config.path;
    path.value = config.effectivePath;
    toast("Thumbnail storage saved");
  } catch (err) {
    error.value = (err as Error).message;
  } finally {
    saving.value = false;
  }
}
onMounted(load);
</script>

<template>
  <section class="flex flex-col gap-3">
    <h3 class="text-xs font-semibold uppercase tracking-wide text-base-content/50">
      Library settings
    </h3>
    <div class="card divide-y divide-base-content/10 bg-base-100">
      <div class="settings-row">
        <div class="flex items-start gap-3">
          <Clock class="mt-0.5 size-5 shrink-0 text-primary" />
          <div>
            <h4 class="text-sm font-medium">Recently added</h4>
            <p class="mt-1 text-xs text-base-content/50">
              Content in the home rail and Recently added
            </p>
          </div>
        </div>
        <div class="min-w-0 xl:col-span-2">
          <div class="dropdown">
            <div
              tabindex="0"
              role="button"
              aria-label="Recently added content"
              class="btn btn-sm h-8 min-h-8 w-44 justify-between gap-2 border border-base-content/20 bg-base-100 px-3 font-normal"
            >
              <span class="truncate text-xs">{{ selectedKindsLabel }}</span>
              <ChevronDown class="size-4 shrink-0 opacity-60" />
            </div>
            <ul
              tabindex="0"
              class="menu dropdown-content z-20 mt-1 w-44 rounded-box bg-base-100 p-2 shadow"
            >
              <li v-for="opt in RECENTLY_ADDED_OPTIONS" :key="opt.value">
                <label class="flex cursor-pointer items-center gap-2.5">
                  <input
                    type="checkbox"
                    class="checkbox checkbox-primary checkbox-xs"
                    :checked="recentlyAddedKinds.includes(opt.value)"
                    :aria-label="opt.label"
                    @change="toggleRecentlyAddedKind(opt.value)"
                  />
                  <span>{{ opt.label }}</span>
                </label>
              </li>
            </ul>
          </div>
        </div>
      </div>

      <div class="settings-row">
        <div class="flex items-start gap-3">
          <Images class="mt-0.5 size-5 shrink-0 text-primary" />
          <div>
            <h4 class="text-sm font-medium">Main bar icons</h4>
            <p class="mt-1 text-xs text-base-content/50">Items visible in the main navigation</p>
          </div>
        </div>
        <div
          class="flex min-w-0 flex-wrap items-center gap-x-8 gap-y-3 xl:col-span-2 xl:self-center"
        >
          <label class="flex items-center gap-3 text-sm">
            <Images class="size-4 text-base-content/60" />
            Comics
            <input
              v-model="mainBarIcons.comics"
              type="checkbox"
              aria-label="Show Comics icon"
              class="toggle toggle-primary toggle-sm"
            />
          </label>
          <label class="flex items-center gap-3 text-sm">
            <GalleryThumbnails class="size-4 text-base-content/60" />
            Gallery
            <input
              v-model="mainBarIcons.gallery"
              type="checkbox"
              aria-label="Show Gallery icon"
              class="toggle toggle-primary toggle-sm"
            />
          </label>
          <label class="flex items-center gap-3 text-sm">
            <Layers class="size-4 text-base-content/60" />
            Lists
            <input
              v-model="mainBarIcons.lists"
              type="checkbox"
              aria-label="Show Lists icon"
              class="toggle toggle-primary toggle-sm"
            />
          </label>
        </div>
      </div>

      <form class="settings-row" @submit.prevent="save">
        <div class="flex items-start gap-3">
          <HardDrive class="mt-0.5 size-5 shrink-0 text-primary" />
          <div>
            <h4 class="text-sm font-medium">Thumbnail storage</h4>
            <p class="mt-1 text-xs text-base-content/50">Folder for covers and gallery previews</p>
          </div>
        </div>
        <div class="flex min-w-0 flex-col gap-3 xl:col-span-2">
          <p v-if="loading" class="text-xs text-base-content/60" role="status">
            Loading storage settings…
          </p>
          <template v-if="ready">
            <ServerPathField
              v-model="path"
              label="Thumbnail folder"
              placeholder="/data/thumbnails"
              browser-title="Choose thumbnail folder"
              :disabled="saving"
            />
            <p v-if="dirty" class="text-xs text-base-content/50">
              Existing thumbnails stay in place; missing ones regenerate here.
            </p>
          </template>
          <p v-if="error" class="text-xs text-error" role="alert">{{ error }}</p>
          <button
            v-if="!ready && !loading"
            type="button"
            class="btn btn-ghost btn-xs self-start"
            @click="load"
          >
            Retry
          </button>
          <div v-if="ready" class="flex flex-wrap items-center justify-between gap-2">
            <span v-if="usingDefault" class="text-xs text-base-content/50">
              Using the default folder
            </span>
            <button
              v-else
              type="button"
              class="btn btn-ghost btn-xs"
              :disabled="saving"
              @click="path = defaultPath"
            >
              Use default folder
            </button>
            <button
              v-if="dirty"
              type="submit"
              class="btn btn-primary btn-xs ml-auto"
              :disabled="saving || !path.trim()"
            >
              {{ saving ? "Saving…" : "Save thumbnail storage" }}
            </button>
          </div>
        </div>
      </form>
      <ImageProcessingSettings />
    </div>
  </section>
</template>
