<script setup lang="ts">
import { Check, Heart, Images, ListPlus } from "lucide-vue-next";
import { computed, ref } from "vue";
import { useRoute } from "vue-router";

import Lightbox from "../components/Lightbox.vue";
import { contentRatingClass, contentRatingLabel } from "../lib/display";
import { toast } from "../lib/toast";
import { findSeries, galleryImages } from "../mocks/library";
import { useCollections } from "../stores/collections";
import type { Collection } from "../types";

const route = useRoute();
const gallery = computed(() => findSeries(String(route.params.id)));
const images = computed(() => galleryImages(gallery.value.id, gallery.value.imageCount ?? 24));

const collections = useCollections();
function toggleList(l: Collection): void {
  const wasIn = collections.hasSeries(l.id, gallery.value.id);
  collections.toggleSeries(l.id, gallery.value.id);
  toast(wasIn ? `Removed from ${l.name}` : `Added to ${l.name}`, wasIn ? "info" : "success");
}
const favorite = ref(gallery.value.favorite ?? false);

// Lightbox
const open = ref(false);
const idx = ref(0);
function openAt(i: number): void {
  idx.value = i;
  open.value = true;
}
</script>

<template>
  <div class="flex flex-col gap-6 p-4 sm:p-6">
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
            <span class="flex items-center gap-1"><Images class="size-3.5" />{{ gallery.imageCount }} images</span>
            <span v-if="gallery.year">· {{ gallery.year }}</span>
            <span class="badge badge-sm" :class="contentRatingClass[gallery.contentRating]">
              {{ contentRatingLabel[gallery.contentRating] }}
            </span>
          </div>
        </div>

        <p v-if="gallery.description" class="text-sm text-base-content/80">{{ gallery.description }}</p>

        <dl class="flex flex-col gap-1.5 text-sm">
          <div v-if="gallery.artists.length" class="flex gap-2">
            <dt class="w-24 shrink-0 text-base-content/50">Artists / models</dt>
            <dd>{{ gallery.artists.join(", ") }}</dd>
          </div>
          <div v-if="gallery.source" class="flex gap-2">
            <dt class="w-24 shrink-0 text-base-content/50">Series</dt>
            <dd>{{ gallery.source }}</dd>
          </div>
          <div v-if="gallery.characters?.length" class="flex gap-2">
            <dt class="w-24 shrink-0 text-base-content/50">Characters</dt>
            <dd class="flex flex-wrap gap-1">
              <span v-for="c in gallery.characters" :key="c" class="badge badge-ghost badge-sm">{{ c }}</span>
            </dd>
          </div>
          <div v-if="gallery.tags.length" class="flex gap-2">
            <dt class="w-24 shrink-0 text-base-content/50">Tags</dt>
            <dd class="flex flex-wrap gap-1">
              <span v-for="tg in gallery.tags" :key="tg.id" class="badge badge-outline badge-sm">{{ tg.name }}</span>
            </dd>
          </div>
        </dl>

        <div class="mt-auto flex flex-wrap items-center gap-2">
          <button class="btn btn-primary btn-sm gap-2" @click="openAt(0)">
            <Images class="size-4" />View
          </button>
          <button
            class="btn btn-square btn-sm"
            :class="{ 'text-error': favorite }"
            aria-label="Favorite"
            @click="favorite = !favorite"
          >
            <Heart class="size-4" :class="{ 'fill-current': favorite }" />
          </button>
          <div class="dropdown dropdown-end">
            <div tabindex="0" role="button" class="btn btn-square btn-sm" aria-label="Add to list">
              <ListPlus class="size-4" />
            </div>
            <ul tabindex="0" class="menu dropdown-content z-10 mt-1 w-56 rounded-box bg-base-100 p-2 shadow">
              <li class="menu-title">Add to list</li>
              <li v-for="l in collections.lists" :key="l.id">
                <a @click="toggleList(l)">
                  <Check class="size-4" :class="collections.hasSeries(l.id, gallery.id) ? 'opacity-100' : 'opacity-0'" />
                  {{ l.name }}
                </a>
              </li>
              <li v-if="!collections.lists.length" class="px-2 py-1 text-xs text-base-content/50">No lists yet</li>
            </ul>
          </div>
        </div>
      </div>
    </section>

    <!-- Image grid -->
    <div class="grid grid-cols-2 gap-2.5 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
      <button
        v-for="(src, i) in images"
        :key="i"
        class="group relative aspect-square overflow-hidden rounded-box surface-border"
        :aria-label="`Open image ${i + 1}`"
        @click="openAt(i)"
      >
        <img
          :src="src"
          alt=""
          loading="lazy"
          class="h-full w-full object-cover transition duration-300 group-hover:scale-105"
        />
      </button>
    </div>

    <Lightbox v-if="open" :images="images" :index="idx" @update:index="idx = $event" @close="open = false" />
  </div>
</template>
