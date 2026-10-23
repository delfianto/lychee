<script setup lang="ts">
import { ChevronDown, Clock, HardDrive } from "@lucide/vue";
import { computed, onMounted, ref } from "vue";
import { fetchThumbnailStorage, saveThumbnailStorage } from "../../api/settingsQueries";
import ServerPathField from "../../components/ServerPathField.vue";
import { RECENTLY_ADDED_OPTIONS, useRecentlyAddedKinds } from "../../lib/density";
import { toast } from "../../lib/toast";

const { recentlyAddedKinds, toggleRecentlyAddedKind } = useRecentlyAddedKinds();
const selectedKindsLabel = computed(() => {
  const labels = RECENTLY_ADDED_OPTIONS.filter((opt) =>
    recentlyAddedKinds.value.includes(opt.value),
  ).map((opt) => opt.label);
  return labels.length ? labels.join(", ") : "None";
});

const mode = ref("default");
const path = ref("");
const defaultPath = ref("");
const savedPath = ref<string | null>(null);
const loading = ref(true);
const saving = ref(false);
const error = ref("");
const ready = ref(false);
const dirty = computed(
  () => (mode.value === "custom" ? path.value.trim() : null) !== savedPath.value,
);

async function load(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const config = await fetchThumbnailStorage();
    defaultPath.value = config.defaultPath;
    savedPath.value = config.path;
    path.value = config.path ?? "";
    mode.value = config.path === null ? "default" : "custom";
    ready.value = true;
  } catch (err) {
    error.value = (err as Error).message;
  } finally {
    loading.value = false;
  }
}

async function save(): Promise<void> {
  saving.value = true;
  error.value = "";
  try {
    const config = await saveThumbnailStorage(mode.value === "custom" ? path.value.trim() : null);
    savedPath.value = config.path;
    path.value = config.path ?? "";
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
    <div class="card bg-base-100">
      <div class="card-body grid gap-6 p-4 lg:grid-cols-2">
        <div class="flex flex-col gap-2">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div class="flex items-start gap-3">
              <Clock class="mt-0.5 size-5 shrink-0 text-primary" />
              <div>
                <h4 class="text-sm font-medium">Recently added</h4>
                <p class="text-xs text-base-content/50">
                  Content shown in the Recently added section
                </p>
              </div>
            </div>
            <div class="dropdown dropdown-end">
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
          <p class="text-xs text-base-content/50">
            Choose which libraries appear in the Recently added rail and feed.
          </p>
        </div>

        <form
          class="flex flex-col gap-2 border-t border-base-content/10 pt-4 lg:border-t-0 lg:border-l lg:pt-0 lg:pl-6"
          @submit.prevent="save"
        >
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div class="flex items-start gap-3">
              <HardDrive class="mt-0.5 size-5 shrink-0 text-primary" />
              <div>
                <h4 class="text-sm font-medium">Thumbnail storage</h4>
                <p class="text-xs text-base-content/50">
                  Cover and gallery thumbnails for all libraries
                </p>
              </div>
            </div>
            <select
              v-if="ready"
              v-model="mode"
              aria-label="Thumbnail storage location"
              class="select select-bordered select-sm w-32 shrink-0"
              :disabled="saving"
            >
              <option value="default">Default folder</option>
              <option value="custom">Custom folder</option>
            </select>
          </div>
          <p v-if="loading" class="text-xs text-base-content/60" role="status">
            Loading storage settings…
          </p>
          <template v-if="ready">
            <ServerPathField
              v-if="mode === 'custom'"
              v-model="path"
              label="Thumbnail folder (absolute path on the server)"
              placeholder="/data/thumbnails"
              browser-title="Choose thumbnail folder"
              :disabled="saving"
            />
            <p v-else class="break-all font-mono text-xs text-base-content/50">
              {{ defaultPath }}
            </p>
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
          <button
            v-if="ready && dirty"
            class="btn btn-primary btn-xs self-end"
            :disabled="saving || (mode === 'custom' && !path.trim())"
          >
            {{ saving ? "Saving…" : "Save thumbnail storage" }}
          </button>
        </form>
      </div>
    </div>
  </section>
</template>
