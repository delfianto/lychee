<script setup lang="ts">
import { Heart, Images, Pencil, Play } from "lucide-vue-next";
import { ref, watch } from "vue";
import { useRoute } from "vue-router";

import { fetchGalleryImages, fetchSeries, patchSeries } from "../api/queries";
import AddToListMenu from "../components/AddToListMenu.vue";
import CoverImage from "../components/CoverImage.vue";
import EditSeriesModal from "../components/EditSeriesModal.vue";
import ErrorState from "../components/ErrorState.vue";
import Lightbox from "../components/Lightbox.vue";
import { contentRatingClass, contentRatingLabel } from "../lib/display";
import type { GalleryMediaItem, Series } from "../types";

const route = useRoute();
const gallery = ref<Series | null>(null);
const items = ref<GalleryMediaItem[]>([]);
const favorite = ref(false);

const failed = ref(false);
async function load(id: string): Promise<void> {
  gallery.value = null;
  failed.value = false;
  try {
    const [g, media] = await Promise.all([fetchSeries(id), fetchGalleryImages(id)]);
    gallery.value = g;
    items.value = media;
    favorite.value = g.favorite ?? false;
  } catch {
    failed.value = true;
  }
}
const reload = (): void => void load(String(route.params.id));
watch(() => route.params.id, (id) => void load(String(id)), { immediate: true });

function toggleFavorite(): void {
  if (!gallery.value) return;
  favorite.value = !favorite.value;
  void patchSeries(gallery.value.id, { favorite: favorite.value });
}

const editOpen = ref(false);
function onEdited(): void {
  editOpen.value = false;
  if (gallery.value) void load(gallery.value.id);
}

// Lightbox
const open = ref(false);
const idx = ref(0);
function openAt(i: number): void {
  idx.value = i;
  open.value = true;
}

/** Grid always uses the small /thumb endpoint — never full-resolution originals. */
function thumbSrc(item: GalleryMediaItem): string {
  return item.thumbUrl || item.posterUrl || item.url;
}
</script>

<template>
  <div class="flex flex-col gap-6 p-4 sm:p-6">
    <ErrorState v-if="failed" message="Couldn't load this gallery." @retry="reload" />
    <div v-else-if="!gallery" class="flex justify-center py-20">
      <span class="loading loading-spinner loading-lg text-primary" />
    </div>
    <template v-else>
      <!-- Header -->
      <section class="flex flex-col gap-4 sm:flex-row sm:gap-6">
        <img
          :src="gallery.coverUrl"
          :alt="gallery.title"
          class="cover w-32 shrink-0 rounded-box object-cover shadow-lg sm:w-40"
        />
        <div class="flex min-w-0 grow flex-col gap-3">
          <div class="flex flex-col gap-1">
            <h1 class="text-2xl font-bold sm:text-3xl">{{ gallery.title }}</h1>
            <div class="flex flex-wrap items-center gap-2 text-xs text-base-content/70">
              <span class="flex items-center gap-1">
                <Images class="size-3.5" />{{ gallery.imageCount }} items
              </span>
              <span v-if="gallery.year">· {{ gallery.year }}</span>
              <span class="badge badge-sm" :class="contentRatingClass[gallery.contentRating]">
                {{ contentRatingLabel[gallery.contentRating] }}
              </span>
            </div>
          </div>

          <p v-if="gallery.description" class="text-sm text-base-content/80">{{ gallery.description }}</p>

          <dl class="flex flex-col gap-1.5 text-sm">
            <div v-if="gallery.artists.length" class="flex gap-2">
              <dt class="w-32 shrink-0 whitespace-nowrap text-base-content/50">Artists / Models</dt>
              <dd>{{ gallery.artists.join(", ") }}</dd>
            </div>
            <div v-if="gallery.source" class="flex gap-2">
              <dt class="w-32 shrink-0 whitespace-nowrap text-base-content/50">Series</dt>
              <dd>{{ gallery.source }}</dd>
            </div>
            <div v-if="gallery.characters?.length" class="flex gap-2">
              <dt class="w-32 shrink-0 whitespace-nowrap text-base-content/50">Characters</dt>
              <dd class="flex flex-wrap gap-1">
                <span v-for="c in gallery.characters" :key="c" class="badge badge-ghost badge-sm">{{ c }}</span>
              </dd>
            </div>
            <div v-if="gallery.tags.length" class="flex gap-2">
              <dt class="w-32 shrink-0 whitespace-nowrap text-base-content/50">Tags</dt>
              <dd class="flex flex-wrap gap-1">
                <span v-for="tg in gallery.tags" :key="tg.id" class="badge badge-outline badge-sm">{{ tg.name }}</span>
              </dd>
            </div>
          </dl>

          <div class="mt-auto flex flex-wrap items-center gap-2">
            <button class="btn btn-primary btn-sm gap-2" :disabled="!items.length" @click="openAt(0)">
              <Images class="size-4" />View
            </button>
            <button
              class="btn btn-square btn-sm"
              :class="{ 'text-error': favorite }"
              aria-label="Favorite"
              @click="toggleFavorite"
            >
              <Heart class="size-4" :class="{ 'fill-current': favorite }" />
            </button>
            <AddToListMenu :series-id="gallery.id" />
            <button class="btn btn-sm gap-2" @click="editOpen = true">
              <Pencil class="size-4" />Edit
            </button>
          </div>
        </div>
      </section>

      <!-- Media grid — CoverImage shimmers while /thumb is generated/fetched -->
      <div class="grid grid-cols-2 gap-2.5 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
        <button
          v-for="item in items"
          :key="item.index"
          class="group relative aspect-square overflow-hidden rounded-box surface-border"
          :aria-label="item.kind === 'video' ? `Play video ${item.index + 1}` : `Open image ${item.index + 1}`"
          @click="openAt(item.index)"
        >
          <CoverImage
            :src="thumbSrc(item)"
            class="absolute inset-0 size-full transition duration-300 group-hover:scale-105"
          />
          <span
            v-if="item.kind === 'video'"
            class="pointer-events-none absolute inset-0 flex items-center justify-center bg-black/25"
          >
            <span class="flex size-10 items-center justify-center rounded-full bg-black/55 text-white shadow">
              <Play class="size-5 fill-current" />
            </span>
          </span>
        </button>
      </div>

      <Lightbox
        v-if="open"
        :items="items"
        :index="idx"
        @update:index="idx = $event"
        @close="open = false"
      />
      <EditSeriesModal v-if="editOpen" :series="gallery" @close="editOpen = false" @saved="onEdited" />
    </template>
  </div>
</template>
