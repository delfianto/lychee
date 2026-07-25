<script setup lang="ts">
// Settings → Appearance: light/dark mode, library density, language, reader
// defaults, and the full community theme picker.
import { ArrowLeftRight, BookOpen, Languages, LayoutGrid, Maximize2, Palette, Sun } from "lucide-vue-next";
import { type Component, ref } from "vue";

import SegmentedToggle from "../../components/SegmentedToggle.vue";
import { type ReaderSettings, useReaderSettings } from "../../lib/readerSettings";
import { THEMES, type Mode, useTheme } from "../../lib/theme";

const { theme, mode, setTheme, setMode } = useTheme();
const themeOptions: { value: Mode; label: string }[] = [
  { value: "dark", label: "Dark" },
  { value: "light", label: "Light" },
];
const themeGroups = [
  { label: "Light", themes: THEMES.filter((t) => t.mode === "light") },
  { label: "Dark", themes: THEMES.filter((t) => t.mode === "dark") },
];

const reader = useReaderSettings();
const readerGroups: { key: keyof ReaderSettings; label: string; desc: string; icon: Component; opts: { value: string; label: string }[] }[] = [
  { key: "mode", label: "Reading mode", desc: "How pages are laid out", icon: BookOpen, opts: [{ value: "single", label: "Single" }, { value: "double", label: "Double" }, { value: "longstrip", label: "Long strip" }] },
  { key: "direction", label: "Direction", desc: "Which way pages turn", icon: ArrowLeftRight, opts: [{ value: "ltr", label: "L → R" }, { value: "rtl", label: "R → L" }] },
  { key: "fit", label: "Fit", desc: "How pages scale to fit", icon: Maximize2, opts: [{ value: "width", label: "Width" }, { value: "height", label: "Height" }, { value: "both", label: "Both" }, { value: "original", label: "Original" }] },
  { key: "background", label: "Background", desc: "Reader page backdrop", icon: Palette, opts: [{ value: "dark", label: "Dark" }, { value: "black", label: "Black" }, { value: "sepia", label: "Sepia" }] },
];
function readerValue(k: keyof ReaderSettings): string {
  return reader[k];
}
function setReader(k: keyof ReaderSettings, v: string): void {
  (reader as unknown as Record<string, string>)[k] = v;
}

const DENSITY_KEY = "lychee.density";
const density = ref(localStorage.getItem(DENSITY_KEY) ?? "list");
function setDensity(d: string): void {
  density.value = d;
  localStorage.setItem(DENSITY_KEY, d);
}
const language = ref("English");
</script>

<template>
  <div class="flex flex-col gap-8">
    <!-- Appearance + Reader side by side -->
    <div class="grid gap-6 lg:grid-cols-2">
      <section class="flex flex-col gap-3">
        <h3 class="text-xs font-semibold uppercase tracking-wide text-base-content/50">Appearance</h3>
        <div class="card grow bg-base-100">
          <div class="card-body gap-4 p-4">
            <div class="flex items-center justify-between gap-4">
              <div class="flex items-start gap-3">
                <Sun class="mt-0.5 size-5 shrink-0 text-primary" />
                <div>
                  <div class="text-sm font-medium">Mode</div>
                  <div class="text-xs text-base-content/50">Flip between your light &amp; dark theme</div>
                </div>
              </div>
              <SegmentedToggle :model-value="mode" :options="themeOptions" aria-label="Theme" @update:model-value="setMode" />
            </div>
            <label class="flex items-center justify-between gap-4">
              <div class="flex items-start gap-3">
                <LayoutGrid class="mt-0.5 size-5 shrink-0 text-primary" />
                <div>
                  <div class="text-sm font-medium">Default library density</div>
                  <div class="text-xs text-base-content/50">How libraries open by default</div>
                </div>
              </div>
              <select
                class="select select-bordered select-sm w-28"
                :value="density"
                @change="setDensity(($event.target as HTMLSelectElement).value)"
              >
                <option value="list">List</option>
                <option value="compact">Compact</option>
                <option value="gallery">Gallery</option>
              </select>
            </label>
            <label class="flex items-center justify-between gap-4">
              <div class="flex items-start gap-3">
                <Languages class="mt-0.5 size-5 shrink-0 text-primary" />
                <div>
                  <div class="text-sm font-medium">Language</div>
                  <div class="text-xs text-base-content/50">Interface language</div>
                </div>
              </div>
              <select v-model="language" class="select select-bordered select-sm w-28">
                <option>English</option>
                <option>日本語</option>
                <option>Español</option>
              </select>
            </label>
          </div>
        </div>
      </section>

      <section class="flex flex-col gap-3">
        <h3 class="text-xs font-semibold uppercase tracking-wide text-base-content/50">Reader defaults</h3>
        <div class="card grow bg-base-100">
          <div class="card-body gap-4 p-4">
            <div v-for="grp in readerGroups" :key="grp.key" class="flex items-center justify-between gap-4">
              <div class="flex items-start gap-3">
                <component :is="grp.icon" class="mt-0.5 size-5 shrink-0 text-primary" />
                <div>
                  <div class="text-sm font-medium">{{ grp.label }}</div>
                  <div class="text-xs text-base-content/50">{{ grp.desc }}</div>
                </div>
              </div>
              <SegmentedToggle
                :model-value="readerValue(grp.key)"
                :options="grp.opts"
                :aria-label="grp.label"
                @update:model-value="(v) => setReader(grp.key, v)"
              />
            </div>
          </div>
        </div>
      </section>
    </div>

    <!-- Theme — full community themes. The Dark/Light toggle above flips
         between your last light and dark pick. -->
    <section class="flex flex-col gap-3">
      <h3 class="text-xs font-semibold uppercase tracking-wide text-base-content/50">Theme</h3>
      <div class="card bg-base-100">
        <div class="card-body gap-4 p-4">
          <div v-for="group in themeGroups" :key="group.label" class="flex flex-col gap-2">
            <div class="text-xs font-medium uppercase tracking-wide text-base-content/40">{{ group.label }}</div>
            <div class="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
              <button
                v-for="t in group.themes"
                :key="t.id"
                class="flex items-center gap-2.5 rounded-lg p-2 text-left transition"
                :class="theme === t.id ? 'bg-base-200 ring-2 ring-primary' : 'hover:bg-base-200'"
                :aria-label="`Use ${t.name} ${group.label} theme`"
                @click="setTheme(t.id)"
              >
                <div
                  :data-theme="t.id"
                  class="grid size-9 shrink-0 grid-cols-2 grid-rows-2 overflow-hidden rounded-md border border-base-300"
                >
                  <div class="bg-base-100"></div>
                  <div class="bg-primary"></div>
                  <div class="bg-secondary"></div>
                  <div class="bg-accent"></div>
                </div>
                <span class="min-w-0 truncate text-xs text-base-content/80">{{ t.name }}</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>
