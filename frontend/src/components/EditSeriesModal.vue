<script setup lang="ts">
import { Plus, X } from "lucide-vue-next";
import { onMounted, reactive, ref } from "vue";

import { fetchTagGroups, patchSeries, type TagGroup } from "../api/queries";
import type { SeriesUpdate } from "../api/client";
import { statusLabel } from "../lib/display";
import { useFocusTrap } from "../lib/focusTrap";
import { demographicLabel, ratingLabel } from "../lib/ratingLabels";
import { toast } from "../lib/toast";
import type { ContentRating, Demographic, PublicationStatus, Series } from "../types";

const props = defineProps<{ series: Series }>();
const emit = defineEmits<{ close: []; saved: [] }>();

// No `open` prop here — the parent mounts this component only while shown, so
// "mounted" is the modal's whole lifetime.
const modalBox = ref<HTMLElement | null>(null);
useFocusTrap(modalBox, ref(true));

const isGallery = props.series.kind === "gallery";

// --- form state (seeded from the series) ---
const form = reactive({
  title: props.series.title,
  description: props.series.description ?? "",
  status: (props.series.status ?? "ongoing") as PublicationStatus,
  contentRating: (props.series.contentRating ?? "safe") as ContentRating,
  demographic: (props.series.demographic ?? "none") as Demographic,
  originCountry: props.series.originCountry ?? "",
  source: props.series.source ?? "",
  authors: [...(props.series.authors ?? [])],
  artists: [...(props.series.artists ?? [])],
  characters: [...(props.series.characters ?? [])],
  tagIds: (props.series.tags ?? []).map((t) => t.id),
});
const yearInput = ref(props.series.year?.toString() ?? "");

// Option lists.
const statuses = Object.keys(statusLabel) as PublicationStatus[];
const ratings: ContentRating[] = ["safe", "suggestive", "erotica", "mature"];
const demographics: Demographic[] = ["none", "shonen", "shojo", "seinen", "josei"];
// Countries limited to the set CountryFlag can render.
const countries: { value: string; label: string }[] = [
  { value: "jp", label: "Japan" },
  { value: "kr", label: "Korea" },
  { value: "cn", label: "China" },
  { value: "tw", label: "Taiwan" },
  { value: "us", label: "United States" },
  { value: "gb", label: "United Kingdom" },
  { value: "fr", label: "France" },
  { value: "de", label: "Germany" },
  { value: "id", label: "Indonesia" },
  { value: "th", label: "Thailand" },
  { value: "vn", label: "Vietnam" },
];

// --- chip inputs (authors / artists / characters) ---
const draft = reactive({ author: "", artist: "", character: "" });
function addChip(list: string[], key: keyof typeof draft): void {
  const value = draft[key].trim();
  if (value && !list.includes(value)) list.push(value);
  draft[key] = "";
}
function removeChip(list: string[], index: number): void {
  list.splice(index, 1);
}

// --- tag picker (pick from the existing taxonomy) ---
const tagGroups = ref<TagGroup[]>([]);
const tagName = reactive<Record<string, string>>({});
onMounted(async () => {
  for (const t of props.series.tags ?? []) tagName[t.id] = t.name;
  tagGroups.value = await fetchTagGroups();
  for (const g of tagGroups.value) for (const t of g.tags) tagName[t.id] = t.name;
});
function toggleTag(id: string): void {
  const i = form.tagIds.indexOf(id);
  if (i === -1) form.tagIds.push(id);
  else form.tagIds.splice(i, 1);
}

// --- save ---
const saving = ref(false);
async function save(): Promise<void> {
  if (!form.title.trim()) {
    toast("Title can't be empty", "error");
    return;
  }
  const year = yearInput.value.trim();
  const payload: SeriesUpdate = {
    title: form.title.trim(),
    description: form.description.trim() || null,
    year: year ? Number(year) : null,
    contentRating: form.contentRating,
    artists: form.artists,
    tagIds: form.tagIds,
  };
  if (isGallery) {
    payload.source = form.source.trim() || null;
    payload.characters = form.characters;
  } else {
    payload.authors = form.authors;
    payload.status = form.status;
    payload.demographic = form.demographic;
    payload.originCountry = form.originCountry || null;
  }
  saving.value = true;
  try {
    await patchSeries(props.series.id, payload);
    toast("Saved");
    emit("saved");
  } catch {
    toast("Couldn't save changes", "error");
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <div class="modal modal-open" @click.self="emit('close')">
    <div ref="modalBox" class="modal-box max-w-2xl">
      <div class="mb-4 flex items-center justify-between">
        <h3 class="text-lg font-bold">{{ isGallery ? "Edit gallery" : "Edit series" }}</h3>
        <button class="btn btn-circle btn-ghost btn-sm" aria-label="Close" @click="emit('close')">
          <X class="size-4" />
        </button>
      </div>

      <div class="flex flex-col gap-4">
        <!-- Title -->
        <label class="form-control">
          <span class="label-text mb-1 text-xs text-base-content/60">
            {{ isGallery ? "Gallery name" : "Title" }}
          </span>
          <input v-model="form.title" class="input input-bordered w-full" />
        </label>

        <!-- People: authors (books only) + artists/models -->
        <div class="grid gap-4 sm:grid-cols-2">
          <div v-if="!isGallery">
            <span class="label-text mb-1 block text-xs text-base-content/60">Authors</span>
            <div class="flex flex-wrap gap-1">
              <span v-for="(a, i) in form.authors" :key="a" class="badge badge-neutral gap-1">
                {{ a }}
                <button aria-label="Remove" @click="removeChip(form.authors, i)"><X class="size-3" /></button>
              </span>
            </div>
            <input
              v-model="draft.author"
              class="input input-bordered input-sm mt-1 w-full"
              placeholder="Add author + Enter"
              @keyup.enter="addChip(form.authors, 'author')"
            />
          </div>

          <div>
            <span class="label-text mb-1 block text-xs text-base-content/60">
              {{ isGallery ? "Artists / Models" : "Artists" }}
            </span>
            <div class="flex flex-wrap gap-1">
              <span v-for="(a, i) in form.artists" :key="a" class="badge badge-neutral gap-1">
                {{ a }}
                <button aria-label="Remove" @click="removeChip(form.artists, i)"><X class="size-3" /></button>
              </span>
            </div>
            <input
              v-model="draft.artist"
              class="input input-bordered input-sm mt-1 w-full"
              placeholder="Add + Enter"
              @keyup.enter="addChip(form.artists, 'artist')"
            />
          </div>
        </div>

        <!-- Gallery: franchise ("Series") + characters -->
        <template v-if="isGallery">
          <label class="form-control">
            <span class="label-text mb-1 text-xs text-base-content/60">Series (franchise)</span>
            <input v-model="form.source" class="input input-bordered w-full" placeholder="e.g. Genshin Impact" />
          </label>
          <div>
            <span class="label-text mb-1 block text-xs text-base-content/60">Characters</span>
            <div class="flex flex-wrap gap-1">
              <span v-for="(c, i) in form.characters" :key="c" class="badge badge-neutral gap-1">
                {{ c }}
                <button aria-label="Remove" @click="removeChip(form.characters, i)"><X class="size-3" /></button>
              </span>
            </div>
            <input
              v-model="draft.character"
              class="input input-bordered input-sm mt-1 w-full"
              placeholder="Add character + Enter"
              @keyup.enter="addChip(form.characters, 'character')"
            />
          </div>
        </template>

        <!-- Attributes -->
        <div class="grid gap-4 sm:grid-cols-3">
          <label v-if="!isGallery" class="form-control">
            <span class="label-text mb-1 text-xs text-base-content/60">Country</span>
            <select v-model="form.originCountry" class="select select-bordered">
              <option value="">—</option>
              <option v-for="c in countries" :key="c.value" :value="c.value">{{ c.label }}</option>
            </select>
          </label>
          <label class="form-control">
            <span class="label-text mb-1 text-xs text-base-content/60">Year</span>
            <input v-model="yearInput" type="number" class="input input-bordered" placeholder="—" />
          </label>
          <label v-if="!isGallery" class="form-control">
            <span class="label-text mb-1 text-xs text-base-content/60">Status</span>
            <select v-model="form.status" class="select select-bordered">
              <option v-for="s in statuses" :key="s" :value="s">{{ statusLabel[s] }}</option>
            </select>
          </label>
          <label class="form-control">
            <span class="label-text mb-1 text-xs text-base-content/60">Content rating</span>
            <select v-model="form.contentRating" class="select select-bordered">
              <option v-for="r in ratings" :key="r" :value="r">{{ ratingLabel(r) }}</option>
            </select>
          </label>
          <label v-if="!isGallery" class="form-control">
            <span class="label-text mb-1 text-xs text-base-content/60">Demographic</span>
            <select v-model="form.demographic" class="select select-bordered">
              <option v-for="d in demographics" :key="d" :value="d">{{ demographicLabel(d) }}</option>
            </select>
          </label>
        </div>

        <!-- Tags (from the existing taxonomy) -->
        <div>
          <span class="label-text mb-1 block text-xs text-base-content/60">Tags</span>
          <div class="mb-1 flex flex-wrap gap-1">
            <span v-for="id in form.tagIds" :key="id" class="badge badge-primary gap-1">
              {{ tagName[id] ?? id }}
              <button aria-label="Remove" @click="toggleTag(id)"><X class="size-3" /></button>
            </span>
            <span v-if="!form.tagIds.length" class="text-xs text-base-content/40">No tags</span>
          </div>
          <div class="dropdown">
            <div tabindex="0" role="button" class="btn btn-sm gap-1"><Plus class="size-4" />Add tags</div>
            <div
              tabindex="0"
              class="dropdown-content z-10 mt-1 max-h-72 w-72 overflow-y-auto rounded-box bg-base-100 p-3 shadow"
            >
              <div v-for="g in tagGroups" :key="g.group" class="mb-3 last:mb-0">
                <div class="mb-1 text-xs font-medium text-base-content/50">{{ g.group }}</div>
                <div class="flex flex-wrap gap-1">
                  <button
                    v-for="t in g.tags"
                    :key="t.id"
                    class="badge badge-sm"
                    :class="form.tagIds.includes(t.id) ? 'badge-primary' : 'badge-outline'"
                    @click="toggleTag(t.id)"
                  >
                    {{ t.name }}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Synopsis -->
        <label class="form-control">
          <span class="label-text mb-1 text-xs text-base-content/60">Synopsis</span>
          <textarea v-model="form.description" class="textarea textarea-bordered min-h-24 w-full" />
        </label>
      </div>

      <div class="modal-action">
        <button class="btn btn-ghost" @click="emit('close')">Cancel</button>
        <button class="btn btn-primary" :disabled="saving" @click="save">
          <span v-if="saving" class="loading loading-spinner loading-sm" />
          Save
        </button>
      </div>
    </div>
  </div>
</template>
