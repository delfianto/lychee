<script setup lang="ts">
// Settings shell: the section rail + the active tab. Each tab's concerns live in
// its own panel under views/settings/ (each owns its state, loads, and SSE wiring).
import { Download, Info, Library, RefreshCw, SlidersHorizontal, Tag } from "@lucide/vue";
import { type Component, computed } from "vue";
import { useRoute, useRouter } from "vue-router";

import AboutPanel from "./settings/AboutPanel.vue";
import AccountsPanel from "./settings/AccountsPanel.vue";
import AppearancePanel from "./settings/AppearancePanel.vue";
import ContentPanel from "./settings/ContentPanel.vue";
import DownloadsPanel from "./settings/DownloadsPanel.vue";
import ImportPanel from "./settings/ImportPanel.vue";
import LibrariesPanel from "./settings/LibrariesPanel.vue";
import ProviderPanel from "./settings/ProviderPanel.vue";
import SyncPanel from "./settings/SyncPanel.vue";

const sections: { key: string; label: string; icon: Component }[] = [
  { key: "general", label: "General", icon: SlidersHorizontal },
  { key: "libraries", label: "Libraries", icon: Library },
  { key: "content", label: "Content", icon: Tag },
  { key: "downloads", label: "Downloads", icon: Download },
  { key: "sync", label: "Sync", icon: RefreshCw },
  { key: "about", label: "About", icon: Info },
];
const route = useRoute();
const router = useRouter();
const active = computed({
  get: () => {
    const section = route.query.section;
    return typeof section === "string" && sections.some((item) => item.key === section)
      ? section
      : "general";
  },
  set: (section: string) => {
    void router.push({ query: { ...route.query, section } });
  },
});
</script>

<template>
  <div class="p-4 sm:p-6">
    <h1 class="mb-6 text-3xl font-bold">Settings</h1>

    <div class="flex max-w-7xl flex-col gap-6 lg:flex-row lg:gap-8">
      <!-- Section rail -->
      <nav
        class="flex gap-1 overflow-x-auto pb-1 lg:w-52 lg:shrink-0 lg:flex-col lg:overflow-visible lg:pb-0"
      >
        <button
          v-for="s in sections"
          :key="s.key"
          class="flex shrink-0 items-center gap-2 whitespace-nowrap rounded-md px-3 py-2 text-sm transition"
          :class="
            active === s.key
              ? 'bg-primary text-primary-content'
              : 'text-base-content/80 hover:bg-base-100'
          "
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
            <div class="grid gap-6 lg:grid-cols-2">
              <ProviderPanel />
              <AccountsPanel />
            </div>
            <AppearancePanel />
          </div>

          <div v-else-if="active === 'libraries'" key="libraries" class="flex flex-col gap-8">
            <LibrariesPanel />
            <ImportPanel />
          </div>

          <ContentPanel v-else-if="active === 'content'" key="content" />
          <DownloadsPanel v-else-if="active === 'downloads'" key="downloads" />
          <SyncPanel v-else-if="active === 'sync'" key="sync" />
          <AboutPanel v-else-if="active === 'about'" key="about" />
        </Transition>
      </div>
    </div>
  </div>
</template>
