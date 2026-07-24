<script setup lang="ts">
import {
  ArrowLeftRight,
  BookOpen,
  Cherry,
  Globe,
  GripVertical,
  Image,
  Info,
  Languages,
  Library,
  LayoutGrid,
  Maximize2,
  Palette,
  Plus,
  Search,
  SlidersHorizontal,
  Sun,
  Tag,
  Wand2,
} from "lucide-vue-next";
import { type Component, reactive, ref } from "vue";

import { type ReaderSettings, useReaderSettings } from "../lib/readerSettings";
import { COLOR_SCHEMES, useTheme } from "../lib/theme";
import { browseTagGroups } from "../mocks/library";
import type { ContentRating } from "../types";

const { theme, setTheme } = useTheme();

// The card-form settings collapse onto one "General" page; the table-heavy
// tag/rating management gets its own page, and About stays separate.
const sections: { key: string; label: string; icon: Component }[] = [
  { key: "general", label: "General", icon: SlidersHorizontal },
  { key: "content", label: "Content", icon: Tag },
  { key: "about", label: "About", icon: Info },
];
const active = ref("general");

// --- Tags (mock) ---
const enabled = reactive<Record<string, boolean>>({});
const usage = reactive<Record<string, number>>({});
browseTagGroups.forEach((g) =>
  g.tags.forEach((t, i) => {
    enabled[t.id] = true;
    usage[t.id] = (i + 2) * 13;
  }),
);

// --- Content ratings (mock; top tier is "Mature") ---
const ratings = reactive<{ key: ContentRating; label: string; level: number; enabled: boolean }[]>([
  { key: "safe", label: "Safe", level: 0, enabled: true },
  { key: "suggestive", label: "Suggestive", level: 1, enabled: true },
  { key: "erotica", label: "Erotica", level: 2, enabled: true },
  { key: "mature", label: "Mature", level: 3, enabled: true },
]);
const levelWidths = ["w-1/4", "w-1/2", "w-3/4", "w-full"];
const levelWidth = (level: number): string => levelWidths[level] ?? "w-full";

// --- Libraries (mock) ---
const libraries = reactive([
  { name: "Manga", path: "/data/manga", series: 128, lastScan: "2h ago" },
  { name: "Comics", path: "/data/comics", series: 42, lastScan: "1d ago" },
]);

// --- Metadata & providers (mock) ---
const provider = reactive({ enabled: true, language: "en", autoMatch: true, fetchCovers: true });
const providerLanguages = ["en", "ja", "ko", "zh"];

// --- Trackers (mock) ---
const trackers = reactive([
  { name: "AniList", connected: true, syncOnRead: true },
  { name: "MyAnimeList", connected: false, syncOnRead: false },
  { name: "MangaUpdates", connected: false, syncOnRead: false },
]);

// --- Reader defaults (shared with the reader) ---
const reader = useReaderSettings();
const readerGroups: { key: keyof ReaderSettings; label: string; icon: Component; opts: { v: string; l: string }[] }[] = [
  { key: "mode", label: "Reading mode", icon: BookOpen, opts: [{ v: "single", l: "Single" }, { v: "double", l: "Double" }, { v: "longstrip", l: "Long strip" }] },
  { key: "direction", label: "Direction", icon: ArrowLeftRight, opts: [{ v: "ltr", l: "L → R" }, { v: "rtl", l: "R → L" }] },
  { key: "fit", label: "Fit", icon: Maximize2, opts: [{ v: "width", l: "Width" }, { v: "height", l: "Height" }, { v: "both", l: "Both" }, { v: "original", l: "Original" }] },
  { key: "background", label: "Background", icon: Palette, opts: [{ v: "dark", l: "Dark" }, { v: "black", l: "Black" }, { v: "sepia", l: "Sepia" }] },
];
function readerValue(k: keyof ReaderSettings): string {
  return reader[k];
}
function setReader(k: keyof ReaderSettings, v: string): void {
  (reader as unknown as Record<string, string>)[k] = v;
}

// --- Appearance ---
const DENSITY_KEY = "lychee.density";
const density = ref(localStorage.getItem(DENSITY_KEY) ?? "list");
function setDensity(d: string): void {
  density.value = d;
  localStorage.setItem(DENSITY_KEY, d);
}
const language = ref("English");

// --- About (mock) ---
const about = { version: "0.1.0-dev", storageUsed: "12.4 GB", pages: "48,120" };
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
        <!-- General: Libraries + Integrations + Preferences -->
        <div v-if="active === 'general'" class="flex flex-col gap-8">
          <!-- Libraries -->
          <section class="flex flex-col gap-3">
            <div class="flex flex-wrap items-center justify-between gap-2">
              <h3 class="text-xs font-semibold uppercase tracking-wide text-base-content/50">Libraries</h3>
              <div class="flex gap-2">
                <button class="btn btn-ghost btn-sm">Scan all</button>
                <button class="btn btn-primary btn-sm gap-1"><Plus class="size-4" />Add library</button>
              </div>
            </div>
            <div class="grid gap-4 lg:grid-cols-2">
              <div v-for="lib in libraries" :key="lib.name" class="card bg-base-100">
                <div class="card-body flex-row flex-wrap items-center gap-4 p-4">
                  <Library class="size-5 shrink-0 text-primary" />
                  <div class="min-w-0 grow">
                    <div class="font-medium">{{ lib.name }}</div>
                    <div class="truncate font-mono text-xs text-base-content/60">{{ lib.path }}</div>
                    <div class="text-xs text-base-content/50">{{ lib.series }} series · scanned {{ lib.lastScan }}</div>
                  </div>
                  <button class="btn btn-ghost btn-sm">Scan</button>
                  <button class="btn btn-ghost btn-sm">Edit</button>
                  <button class="btn btn-ghost btn-sm text-error">Remove</button>
                </div>
              </div>
            </div>
          </section>

          <!-- Providers + Trackers side by side -->
          <div class="grid items-start gap-6 lg:grid-cols-2">
            <section class="flex flex-col gap-3">
              <h3 class="text-xs font-semibold uppercase tracking-wide text-base-content/50">Metadata providers</h3>
              <div class="card bg-base-100">
                <div class="card-body gap-4 p-4">
                  <div class="flex items-center justify-between gap-4">
                    <div class="flex items-start gap-3">
                      <Globe class="mt-0.5 size-5 shrink-0 text-primary" />
                      <div>
                        <div class="text-sm font-medium">MangaDex</div>
                        <div class="text-xs text-base-content/50">Primary metadata source &amp; optional chapter downloader</div>
                      </div>
                    </div>
                    <input v-model="provider.enabled" type="checkbox" class="toggle toggle-primary" />
                  </div>
                  <label class="flex items-center justify-between gap-4">
                    <div class="flex items-start gap-3">
                      <Languages class="mt-0.5 size-5 shrink-0 text-primary" />
                      <div>
                        <div class="text-sm font-medium">Preferred language</div>
                        <div class="text-xs text-base-content/50">Fetch metadata &amp; chapters in this language when available</div>
                      </div>
                    </div>
                    <select v-model="provider.language" class="select select-bordered select-sm w-28">
                      <option v-for="l in providerLanguages" :key="l">{{ l }}</option>
                    </select>
                  </label>
                  <label class="flex items-center justify-between gap-4">
                    <div class="flex items-start gap-3">
                      <Wand2 class="mt-0.5 size-5 shrink-0 text-primary" />
                      <div>
                        <div class="text-sm font-medium">Auto-match on scan</div>
                        <div class="text-xs text-base-content/50">Match new series to MangaDex automatically after each scan</div>
                      </div>
                    </div>
                    <input v-model="provider.autoMatch" type="checkbox" class="toggle toggle-primary toggle-sm" />
                  </label>
                  <label class="flex items-center justify-between gap-4">
                    <div class="flex items-start gap-3">
                      <Image class="mt-0.5 size-5 shrink-0 text-primary" />
                      <div>
                        <div class="text-sm font-medium">Download covers</div>
                        <div class="text-xs text-base-content/50">Fetch cover art from the provider when a series has none</div>
                      </div>
                    </div>
                    <input v-model="provider.fetchCovers" type="checkbox" class="toggle toggle-primary toggle-sm" />
                  </label>
                </div>
              </div>
            </section>

            <section class="flex flex-col gap-3">
              <h3 class="text-xs font-semibold uppercase tracking-wide text-base-content/50">Trackers</h3>
              <div class="card bg-base-100">
                <div class="card-body gap-4 p-4">
                  <div v-for="t in trackers" :key="t.name" class="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <div class="text-sm font-medium">{{ t.name }}</div>
                      <div class="text-xs" :class="t.connected ? 'text-success' : 'text-base-content/50'">
                        {{ t.connected ? "Connected" : "Not connected" }}
                      </div>
                    </div>
                    <div class="flex items-center gap-3">
                      <label v-if="t.connected" class="flex items-center gap-2 text-xs text-base-content/60">
                        Sync on read
                        <input v-model="t.syncOnRead" type="checkbox" class="toggle toggle-primary toggle-sm" />
                      </label>
                      <button
                        class="btn btn-sm"
                        :class="t.connected ? 'btn-ghost text-error' : 'btn-primary'"
                        @click="t.connected = !t.connected"
                      >
                        {{ t.connected ? "Disconnect" : "Connect" }}
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </section>
          </div>

          <!-- Appearance + Reader side by side -->
          <div class="grid items-start gap-6 lg:grid-cols-2">
            <section class="flex flex-col gap-3">
              <h3 class="text-xs font-semibold uppercase tracking-wide text-base-content/50">Appearance</h3>
              <div class="card bg-base-100">
                <div class="card-body gap-4 p-4">
                  <div class="flex items-center justify-between gap-4">
                    <div class="flex items-start gap-3">
                      <Sun class="mt-0.5 size-5 shrink-0 text-primary" />
                      <div>
                        <div class="text-sm font-medium">Theme</div>
                        <div class="text-xs text-base-content/50">Dark or light interface</div>
                      </div>
                    </div>
                    <div class="join">
                      <button class="btn btn-sm join-item" :class="theme === 'dark' ? 'btn-primary' : 'btn-ghost'" @click="setTheme('dark')">Dark</button>
                      <button class="btn btn-sm join-item" :class="theme === 'light' ? 'btn-primary' : 'btn-ghost'" @click="setTheme('light')">Light</button>
                    </div>
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
              <div class="card bg-base-100">
                <div class="card-body gap-4 p-4">
                  <div v-for="grp in readerGroups" :key="grp.key" class="flex flex-wrap items-center justify-between gap-3">
                    <div class="flex items-center gap-3">
                      <component :is="grp.icon" class="size-5 shrink-0 text-primary" />
                      <span class="text-sm font-medium">{{ grp.label }}</span>
                    </div>
                    <div class="join">
                      <button
                        v-for="o in grp.opts"
                        :key="o.v"
                        class="btn btn-sm join-item"
                        :class="readerValue(grp.key) === o.v ? 'btn-primary' : 'btn-ghost'"
                        @click="setReader(grp.key, o.v)"
                      >
                        {{ o.l }}
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </section>
          </div>

          <!-- Color scheme -->
          <section class="flex flex-col gap-3">
            <h3 class="text-xs font-semibold uppercase tracking-wide text-base-content/50">Color scheme</h3>
            <div class="card bg-base-100">
              <div class="card-body p-4">
                <div class="grid grid-cols-3 gap-3 sm:grid-cols-5 md:grid-cols-6 lg:grid-cols-8">
                  <button
                    v-for="scheme in COLOR_SCHEMES"
                    :key="scheme"
                    class="flex flex-col items-center gap-1.5 rounded-lg p-1.5 transition"
                    :class="theme === scheme ? 'bg-base-200 ring-2 ring-primary' : 'hover:bg-base-200'"
                    :aria-label="`Use ${scheme} theme`"
                    @click="setTheme(scheme)"
                  >
                    <div
                      :data-theme="scheme"
                      class="grid size-11 grid-cols-2 grid-rows-2 overflow-hidden rounded-md border border-base-300"
                    >
                      <div class="bg-base-100"></div>
                      <div class="bg-primary"></div>
                      <div class="bg-secondary"></div>
                      <div class="bg-accent"></div>
                    </div>
                    <span class="text-xs capitalize text-base-content/70">{{ scheme }}</span>
                  </button>
                </div>
              </div>
            </div>
          </section>
        </div>

        <!-- Content: Tags + Content rating -->
        <div v-else-if="active === 'content'" class="flex flex-col gap-8">
          <section class="flex flex-col gap-3">
            <div class="flex flex-wrap items-center justify-between gap-2">
              <h3 class="text-xs font-semibold uppercase tracking-wide text-base-content/50">Tags</h3>
              <div class="flex items-center gap-2">
                <label class="input input-bordered input-sm flex items-center gap-2">
                  <Search class="size-4 opacity-60" />
                  <input type="search" class="grow" placeholder="Search tags…" />
                </label>
                <button class="btn btn-primary btn-sm gap-1"><Plus class="size-4" />Add tag</button>
              </div>
            </div>
            <div v-for="g in browseTagGroups" :key="g.group" class="card bg-base-100">
              <div class="card-body gap-2 p-4">
                <h4 class="text-sm font-semibold text-base-content/70">{{ g.group }}</h4>
                <div class="overflow-x-auto">
                  <table class="table table-sm">
                    <tbody>
                      <tr v-for="t in g.tags" :key="t.id">
                        <td class="w-6 cursor-grab text-base-content/40"><GripVertical class="size-4" /></td>
                        <td class="font-medium">{{ t.name }}</td>
                        <td><span class="badge badge-ghost badge-sm">default</span></td>
                        <td class="text-xs text-base-content/60">{{ usage[t.id] }} uses</td>
                        <td>
                          <input v-model="enabled[t.id]" type="checkbox" class="toggle toggle-primary toggle-sm" />
                        </td>
                        <td class="text-right">
                          <button class="btn btn-ghost btn-xs">Edit</button>
                          <button class="btn btn-ghost btn-xs text-error" disabled>Delete</button>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </section>

          <section class="flex flex-col gap-3">
            <h3 class="text-xs font-semibold uppercase tracking-wide text-base-content/50">Content rating</h3>
            <div class="card bg-base-100">
              <div class="card-body gap-4 p-4">
                <div v-for="r in ratings" :key="r.key" class="flex items-center gap-4">
                  <span class="w-24 shrink-0 font-medium">{{ r.label }}</span>
                  <div class="h-2 grow overflow-hidden rounded-full bg-base-300">
                    <div class="h-2 rounded-full bg-primary" :class="levelWidth(r.level)"></div>
                  </div>
                  <span class="w-16 shrink-0 text-right text-xs text-base-content/60">level {{ r.level }}</span>
                  <input v-model="r.enabled" type="checkbox" class="toggle toggle-primary toggle-sm" />
                </div>
              </div>
            </div>
            <p class="text-xs text-base-content/60">Higher level = more explicit. Drives per-library content filtering.</p>
          </section>
        </div>

        <!-- About -->
        <div v-else-if="active === 'about'" class="flex flex-col gap-3">
          <h3 class="text-xs font-semibold uppercase tracking-wide text-base-content/50">About</h3>
          <div class="card bg-base-100">
            <div class="card-body gap-3 p-4">
              <div class="flex items-center gap-3">
                <Cherry class="size-8 text-primary" />
                <div>
                  <div class="text-lg font-bold">lychee</div>
                  <div class="text-xs text-base-content/60">v{{ about.version }}</div>
                </div>
              </div>
              <div class="divider my-0"></div>
              <div class="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <div class="text-xs text-base-content/60">Storage used</div>
                  <div>{{ about.storageUsed }}</div>
                </div>
                <div>
                  <div class="text-xs text-base-content/60">Pages indexed</div>
                  <div>{{ about.pages }}</div>
                </div>
              </div>
              <div class="flex gap-2">
                <a class="btn btn-ghost btn-sm" href="#">GitHub</a>
                <a class="btn btn-ghost btn-sm" href="#">Docs</a>
              </div>
            </div>
          </div>
          <p class="text-xs text-base-content/60">Self-hosted manga &amp; comic server.</p>
        </div>
      </div>
    </div>
  </div>
</template>
