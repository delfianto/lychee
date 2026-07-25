<script setup lang="ts">
// Settings shell: the section rail + the active tab. Each tab's concerns live in
// its own panel under views/settings/ (each owns its state, loads, and SSE wiring).
import { Download, Info, SlidersHorizontal, Tag } from "lucide-vue-next";
import { type Component, ref } from "vue";

import AboutPanel from "./settings/AboutPanel.vue";
import AppearancePanel from "./settings/AppearancePanel.vue";
import ContentPanel from "./settings/ContentPanel.vue";
import DownloadsPanel from "./settings/DownloadsPanel.vue";
import LibrariesPanel from "./settings/LibrariesPanel.vue";
import ProviderPanel from "./settings/ProviderPanel.vue";
import TrackersPanel from "./settings/TrackersPanel.vue";

const sections: { key: string; label: string; icon: Component }[] = [
  { key: "general", label: "General", icon: SlidersHorizontal },
  { key: "content", label: "Content", icon: Tag },
  { key: "downloads", label: "Downloads", icon: Download },
  { key: "about", label: "About", icon: Info },
];
const active = ref("general");
</script>

<template>
  <div class="p-4 sm:p-6">
    <h1 class="mb-6 text-3xl font-bold">Settings</h1>

    <div class="flex max-w-7xl flex-col gap-6 lg:flex-row lg:gap-8">
      <!-- Section rail -->
      <nav class="flex gap-1 overflow-x-auto pb-1 lg:w-52 lg:shrink-0 lg:flex-col lg:overflow-visible lg:pb-0">
        <button
          v-for="s in sections"
          :key="s.key"
          class="flex shrink-0 items-center gap-2 whitespace-nowrap rounded-md px-3 py-2 text-sm transition"
          :class="active === s.key ? 'bg-primary text-primary-content' : 'text-base-content/80 hover:bg-base-100'"
          @click="active = s.key"
        >
          <component :is="s.icon" class="size-4 shrink-0" />{{ s.label }}
        </button>
      </nav>

      <!-- Content pane -->
      <div class="min-w-0 grow">
        <!-- Fade between sub-tabs (same transition as page navigation). Distinct
             keys are required or Vue reuses the <div> and skips the animation. -->
        <Transition name="page" mode="out-in">
          <div v-if="active === 'general'" key="general" class="flex flex-col gap-8">
            <LibrariesPanel />
            <div class="grid gap-6 lg:grid-cols-2">
              <ProviderPanel />
              <TrackersPanel />
            </div>
            <AppearancePanel />
          </div>

          <ContentPanel v-else-if="active === 'content'" key="content" />
          <DownloadsPanel v-else-if="active === 'downloads'" key="downloads" />
          <AboutPanel v-else-if="active === 'about'" key="about" />
        </Transition>
      </div>
    </div>
  </div>
</template>
