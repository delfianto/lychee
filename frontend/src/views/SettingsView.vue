<script setup lang="ts">
import { Cherry, GripVertical, Plus, Search } from "lucide-vue-next";
import { reactive, ref } from "vue";

import { type ReaderSettings, useReaderSettings } from "../lib/readerSettings";
import { useTheme } from "../lib/theme";
import { browseTagGroups } from "../mocks/library";
import type { ContentRating } from "../types";

const { theme, toggle } = useTheme();

const sections = [
  { key: "libraries", label: "Libraries" },
  { key: "tags", label: "Tags" },
  { key: "rating", label: "Content Rating" },
  { key: "providers", label: "Metadata & Providers" },
  { key: "trackers", label: "Trackers" },
  { key: "reader", label: "Reader" },
  { key: "appearance", label: "Appearance" },
  { key: "about", label: "About" },
];
const active = ref("libraries");

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
const readerGroups: { key: keyof ReaderSettings; label: string; opts: { v: string; l: string }[] }[] = [
  { key: "mode", label: "Reading mode", opts: [{ v: "single", l: "Single" }, { v: "double", l: "Double" }, { v: "longstrip", l: "Long strip" }] },
  { key: "direction", label: "Direction", opts: [{ v: "ltr", l: "L → R" }, { v: "rtl", l: "R → L" }] },
  { key: "fit", label: "Fit", opts: [{ v: "width", l: "Width" }, { v: "height", l: "Height" }, { v: "both", l: "Both" }, { v: "original", l: "Original" }] },
  { key: "background", label: "Background", opts: [{ v: "dark", l: "Dark" }, { v: "black", l: "Black" }, { v: "sepia", l: "Sepia" }] },
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
  <div class="flex flex-col gap-6 p-4 sm:p-6">
    <!-- Section tabs -->
    <div role="tablist" class="tabs tabs-border overflow-x-auto">
      <a
        v-for="s in sections"
        :key="s.key"
        role="tab"
        class="tab whitespace-nowrap"
        :class="{ 'tab-active': active === s.key }"
        @click="active = s.key"
      >
        {{ s.label }}
      </a>
    </div>

    <div class="min-w-0">
      <!-- Libraries -->
      <div v-if="active === 'libraries'" class="flex flex-col gap-4">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <h2 class="text-lg font-semibold">Libraries</h2>
          <div class="flex gap-2">
            <button class="btn btn-ghost btn-sm">Scan all</button>
            <button class="btn btn-primary btn-sm gap-1"><Plus class="size-4" />Add library</button>
          </div>
        </div>
        <div v-for="lib in libraries" :key="lib.name" class="card bg-base-100">
          <div class="card-body flex-row flex-wrap items-center gap-4 p-4">
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

      <!-- Tags -->
      <div v-else-if="active === 'tags'" class="flex flex-col gap-4">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <h2 class="text-lg font-semibold">Tags</h2>
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
            <h3 class="text-sm font-semibold text-base-content/70">{{ g.group }}</h3>
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
      </div>

      <!-- Content rating -->
      <div v-else-if="active === 'rating'" class="flex flex-col gap-4">
        <h2 class="text-lg font-semibold">Content Rating</h2>
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
      </div>

      <!-- Metadata & providers -->
      <div v-else-if="active === 'providers'" class="flex flex-col gap-4">
        <h2 class="text-lg font-semibold">Metadata &amp; Providers</h2>
        <div class="card bg-base-100">
          <div class="card-body gap-4 p-4">
            <div class="flex items-center justify-between gap-4">
              <div>
                <div class="font-medium">MangaDex</div>
                <div class="text-xs text-base-content/60">Primary metadata source &amp; optional chapter downloader</div>
              </div>
              <input v-model="provider.enabled" type="checkbox" class="toggle toggle-primary" />
            </div>
            <div class="divider my-0"></div>
            <label class="flex items-center justify-between gap-4">
              <span class="text-sm">Preferred language</span>
              <select v-model="provider.language" class="select select-bordered select-sm w-40">
                <option v-for="l in providerLanguages" :key="l">{{ l }}</option>
              </select>
            </label>
            <label class="flex items-center justify-between gap-4">
              <span class="text-sm">Auto-match on scan</span>
              <input v-model="provider.autoMatch" type="checkbox" class="toggle toggle-primary toggle-sm" />
            </label>
            <label class="flex items-center justify-between gap-4">
              <span class="text-sm">Download covers</span>
              <input v-model="provider.fetchCovers" type="checkbox" class="toggle toggle-primary toggle-sm" />
            </label>
          </div>
        </div>
        <p class="text-xs text-base-content/60">Providers are queried in priority order to fill missing metadata.</p>
      </div>

      <!-- Trackers -->
      <div v-else-if="active === 'trackers'" class="flex flex-col gap-4">
        <h2 class="text-lg font-semibold">Trackers</h2>
        <div v-for="t in trackers" :key="t.name" class="card bg-base-100">
          <div class="card-body flex-row flex-wrap items-center gap-4 p-4">
            <div class="grow">
              <div class="font-medium">{{ t.name }}</div>
              <div class="text-xs" :class="t.connected ? 'text-success' : 'text-base-content/50'">
                {{ t.connected ? "Connected" : "Not connected" }}
              </div>
            </div>
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

      <!-- Reader defaults -->
      <div v-else-if="active === 'reader'" class="flex flex-col gap-4">
        <h2 class="text-lg font-semibold">Reader defaults</h2>
        <div class="card bg-base-100">
          <div class="card-body gap-4 p-4">
            <div v-for="grp in readerGroups" :key="grp.key">
              <div class="mb-1 text-sm font-medium">{{ grp.label }}</div>
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
        <p class="text-xs text-base-content/60">Defaults for newly opened chapters; per-series overrides stick.</p>
      </div>

      <!-- Appearance -->
      <div v-else-if="active === 'appearance'" class="flex flex-col gap-4">
        <h2 class="text-lg font-semibold">Appearance</h2>
        <div class="card bg-base-100">
          <div class="card-body gap-4 p-4">
            <div class="flex items-center justify-between gap-4">
              <span class="text-sm font-medium">Theme</span>
              <div class="join">
                <button class="btn btn-sm join-item" :class="theme === 'dark' ? 'btn-primary' : 'btn-ghost'" @click="theme !== 'dark' && toggle()">Dark</button>
                <button class="btn btn-sm join-item" :class="theme === 'light' ? 'btn-primary' : 'btn-ghost'" @click="theme !== 'light' && toggle()">Light</button>
              </div>
            </div>
            <label class="flex items-center justify-between gap-4">
              <span class="text-sm font-medium">Default library density</span>
              <select
                class="select select-bordered select-sm w-40"
                :value="density"
                @change="setDensity(($event.target as HTMLSelectElement).value)"
              >
                <option value="list">List</option>
                <option value="compact">Compact</option>
                <option value="gallery">Gallery</option>
              </select>
            </label>
            <label class="flex items-center justify-between gap-4">
              <span class="text-sm font-medium">Language</span>
              <select v-model="language" class="select select-bordered select-sm w-40">
                <option>English</option>
                <option>日本語</option>
                <option>Español</option>
              </select>
            </label>
          </div>
        </div>
      </div>

      <!-- About -->
      <div v-else-if="active === 'about'" class="flex flex-col gap-4">
        <h2 class="text-lg font-semibold">About</h2>
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
</template>
