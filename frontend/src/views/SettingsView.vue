<script setup lang="ts">
import {
  ArrowLeftRight,
  BookOpen,
  BookText,
  Bug,
  Check,
  Cherry,
  Download,
  Github,
  Globe,
  Image,
  Info,
  Languages,
  Library,
  LayoutGrid,
  Link2,
  Maximize2,
  Palette,
  Pause,
  Play,
  Plus,
  RefreshCw,
  Search,
  SlidersHorizontal,
  Sun,
  Tag,
  Wand2,
  X,
} from "lucide-vue-next";
import { type Component, computed, reactive, ref, watch } from "vue";

import SegmentedToggle from "../components/SegmentedToggle.vue";
import { type ReaderSettings, useReaderSettings } from "../lib/readerSettings";
import { THEMES, type Mode, useTheme } from "../lib/theme";
import {
  browseTagGroups,
  type DownloadTask,
  downloads,
  librarySeries,
  librarySummaries,
  syncStatus,
} from "../mocks/library";
import type { ContentRating, Demographic } from "../types";

const { theme, mode, setTheme, setMode } = useTheme();
const themeOptions: { value: Mode; label: string }[] = [
  { value: "dark", label: "Dark" },
  { value: "light", label: "Light" },
];
const themeGroups = [
  { label: "Light", themes: THEMES.filter((t) => t.mode === "light") },
  { label: "Dark", themes: THEMES.filter((t) => t.mode === "dark") },
];

// The card-form settings collapse onto one "General" page; the table-heavy
// tag/rating management gets its own page, and About stays separate.
const sections: { key: string; label: string; icon: Component }[] = [
  { key: "general", label: "General", icon: SlidersHorizontal },
  { key: "content", label: "Content", icon: Tag },
  { key: "downloads", label: "Downloads", icon: Download },
  { key: "about", label: "About", icon: Info },
];
const active = ref("general");

// --- Content taxonomy: one table over tags, content ratings and demographics.
// Each row has a parent category ("type"); usage counts are derived from the
// library. (A real MangaDex-style taxonomy comes with the backend.) ---
interface TaxRow {
  id: string;
  name: string;
  category: string;
  uses: number;
  enabled: boolean;
}
const ratingTiers: { key: ContentRating; label: string }[] = [
  { key: "safe", label: "Safe" },
  { key: "suggestive", label: "Suggestive" },
  { key: "erotica", label: "Erotica" },
  { key: "mature", label: "Mature" },
];
const demoTiers: { key: Demographic; label: string }[] = [
  { key: "shonen", label: "Shounen" },
  { key: "shojo", label: "Shoujo" },
  { key: "seinen", label: "Seinen" },
  { key: "josei", label: "Josei" },
];
const tagUses = (id: string): number => librarySeries.filter((s) => s.tags.some((t) => t.id === id)).length;
const taxonomy = reactive<TaxRow[]>([
  ...browseTagGroups.flatMap((g) =>
    g.tags.map((t) => ({ id: t.id, name: t.name, category: g.group, uses: tagUses(t.id), enabled: true })),
  ),
  ...ratingTiers.map((r) => ({
    id: `cr-${r.key}`,
    name: r.label,
    category: "Content Rating",
    uses: librarySeries.filter((s) => s.contentRating === r.key).length,
    enabled: true,
  })),
  ...demoTiers.map((d) => ({
    id: `demo-${d.key}`,
    name: d.label,
    category: "Demographic",
    uses: librarySeries.filter((s) => s.demographic === d.key).length,
    enabled: true,
  })),
]);
const taxCategories = [...new Set(taxonomy.map((r) => r.category))].sort();
const taxSearch = ref("");
const taxCat = ref("");
const taxPage = ref(0);
const TAX_PAGE_SIZE = 20;
const taxFiltered = computed(() => {
  const q = taxSearch.value.trim().toLowerCase();
  return taxonomy.filter(
    (r) => (!q || r.name.toLowerCase().includes(q)) && (!taxCat.value || r.category === taxCat.value),
  );
});
const taxPageCount = computed(() => Math.max(1, Math.ceil(taxFiltered.value.length / TAX_PAGE_SIZE)));
const taxRows = computed(() =>
  taxFiltered.value.slice(taxPage.value * TAX_PAGE_SIZE, taxPage.value * TAX_PAGE_SIZE + TAX_PAGE_SIZE),
);
watch([taxSearch, taxCat], () => (taxPage.value = 0));
function removeTax(row: TaxRow): void {
  const i = taxonomy.indexOf(row);
  if (i >= 0) taxonomy.splice(i, 1);
}

// --- Downloads + MangaDex sync (mock) ---
const dl = reactive<DownloadTask[]>(downloads.map((d) => ({ ...d })));
const sync = reactive({ ...syncStatus, syncing: false });
const dlLabel: Record<string, string> = {
  downloading: "Downloading",
  queued: "Queued",
  paused: "Paused",
  done: "Done",
  failed: "Failed",
};
const dlBadge: Record<string, string> = {
  downloading: "badge-primary",
  queued: "badge-ghost",
  paused: "badge-warning",
  done: "badge-success",
  failed: "badge-error",
};
const hasDone = computed(() => dl.some((d) => d.status === "done"));
function syncNow(): void {
  sync.syncing = true;
  setTimeout(() => {
    sync.syncing = false;
    sync.lastSync = "just now";
  }, 1500);
}
function retryDownload(d: DownloadTask): void {
  d.status = "downloading";
  d.progress = 0;
}
function removeDownload(d: DownloadTask): void {
  const i = dl.indexOf(d);
  if (i >= 0) dl.splice(i, 1);
}
function clearDone(): void {
  for (let i = dl.length - 1; i >= 0; i--) if (dl[i].status === "done") dl.splice(i, 1);
}

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
  { name: "NovelUpdates", connected: false, syncOnRead: false },
]);

// --- Reader defaults (shared with the reader) ---
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

// --- Appearance ---
const DENSITY_KEY = "lychee.density";
const density = ref(localStorage.getItem(DENSITY_KEY) ?? "list");
function setDensity(d: string): void {
  density.value = d;
  localStorage.setItem(DENSITY_KEY, d);
}
const language = ref("English");

// --- About (mock) ---
const about = {
  version: "0.1.0-dev",
  build: "a3efc06",
  platform: "Linux · x86_64",
  database: "SQLite · 84 MB",
  uptime: "6d 14h",
  started: "Jul 18, 2026",
};
const nonGallery = librarySeries.filter((s) => s.kind !== "gallery");
const libStats = [
  { label: "Series", value: nonGallery.length.toLocaleString() },
  { label: "Chapters", value: nonGallery.reduce((n, s) => n + s.chapterCount, 0).toLocaleString() },
  { label: "Galleries", value: librarySeries.filter((s) => s.kind === "gallery").length.toLocaleString() },
  { label: "Storage", value: `${librarySummaries.reduce((n, l) => n + l.sizeGb, 0).toFixed(1)} GB` },
];
const serverInfo = [
  { label: "Version", value: about.version },
  { label: "Build", value: about.build },
  { label: "Platform", value: about.platform },
  { label: "Database", value: about.database },
  { label: "Uptime", value: about.uptime },
  { label: "Started", value: about.started },
];
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
        <!-- General: Libraries + Integrations + Preferences -->
        <div v-if="active === 'general'" key="general" class="flex flex-col gap-8">
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
          <div class="grid gap-6 lg:grid-cols-2">
            <section class="flex flex-col gap-3">
              <h3 class="text-xs font-semibold uppercase tracking-wide text-base-content/50">Metadata providers</h3>
              <div class="card grow bg-base-100">
                <div class="card-body gap-4 p-4">
                  <div class="flex items-center justify-between gap-4">
                    <div class="flex items-start gap-3">
                      <Globe class="mt-0.5 size-5 shrink-0 text-primary" />
                      <div>
                        <div class="text-sm font-medium">MangaDex</div>
                        <div class="text-xs text-base-content/50">Primary metadata source &amp; optional chapter downloader</div>
                      </div>
                    </div>
                    <input v-model="provider.enabled" type="checkbox" class="toggle toggle-primary toggle-sm" />
                  </div>
                  <label class="flex items-center justify-between gap-4">
                    <div class="flex items-start gap-3">
                      <Languages class="mt-0.5 size-5 shrink-0 text-primary" />
                      <div>
                        <div class="text-sm font-medium">Preferred language</div>
                        <div class="text-xs text-base-content/50">Fetch metadata &amp; chapters in this language</div>
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
              <div class="card grow bg-base-100">
                <div class="card-body gap-4 p-4">
                  <div v-for="t in trackers" :key="t.name" class="flex flex-wrap items-center justify-between gap-4">
                    <div class="flex items-start gap-3">
                      <Link2 class="mt-0.5 size-5 shrink-0 text-primary" />
                      <div>
                        <div class="text-sm font-medium">{{ t.name }}</div>
                        <div class="text-xs" :class="t.connected ? 'text-success' : 'text-base-content/50'">
                          {{ t.connected ? "Connected" : "Not connected" }}
                        </div>
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

        <!-- Content: one taxonomy table (tags · content ratings · demographics) -->
        <div v-else-if="active === 'content'" key="content" class="flex flex-col gap-4">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <h3 class="text-xs font-semibold uppercase tracking-wide text-base-content/50">Content taxonomy</h3>
            <button class="btn btn-primary btn-sm gap-1"><Plus class="size-4" />Add</button>
          </div>

          <!-- Search + type filter -->
          <div class="flex flex-wrap items-center gap-2">
            <label class="input input-bordered input-sm flex w-full max-w-xs items-center gap-2">
              <Search class="size-4 opacity-60" />
              <input v-model="taxSearch" type="search" class="grow" placeholder="Search name…" />
            </label>
            <select v-model="taxCat" class="select select-bordered select-sm" aria-label="Filter by type">
              <option value="">All types</option>
              <option v-for="c in taxCategories" :key="c">{{ c }}</option>
            </select>
          </div>

          <!-- Unified table -->
          <div class="card bg-base-100">
            <div class="card-body p-0">
              <div class="overflow-x-auto">
                <table class="table">
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Type</th>
                      <th>Uses</th>
                      <th>Enabled</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="row in taxRows" :key="row.id" class="hover:bg-base-200/50">
                      <td class="font-medium">{{ row.name }}</td>
                      <td><span class="badge badge-ghost badge-sm whitespace-nowrap">{{ row.category }}</span></td>
                      <td class="text-base-content/60">{{ row.uses }}</td>
                      <td>
                        <input v-model="row.enabled" type="checkbox" class="toggle toggle-primary toggle-sm" />
                      </td>
                      <td class="whitespace-nowrap text-right">
                        <button class="btn btn-ghost btn-xs">Edit</button>
                        <button class="btn btn-ghost btn-xs text-error" @click="removeTax(row)">Delete</button>
                      </td>
                    </tr>
                    <tr v-if="!taxRows.length">
                      <td colspan="5" class="py-8 text-center text-sm text-base-content/50">No entries match.</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <!-- Pagination -->
          <div class="flex items-center justify-between">
            <span class="text-xs text-base-content/60">
              {{ taxFiltered.length }} entries · page {{ taxPage + 1 }} of {{ taxPageCount }}
            </span>
            <div class="join">
              <button class="btn btn-sm join-item" :disabled="taxPage === 0" @click="taxPage--">Prev</button>
              <button class="btn btn-sm join-item" :disabled="taxPage >= taxPageCount - 1" @click="taxPage++">
                Next
              </button>
            </div>
          </div>
        </div>

        <!-- About -->
        <!-- Downloads + MangaDex sync -->
        <div v-else-if="active === 'downloads'" key="downloads" class="flex flex-col gap-6">
          <section class="flex flex-col gap-3">
            <h3 class="text-xs font-semibold uppercase tracking-wide text-base-content/50">Sync</h3>
            <div class="card bg-base-100">
              <div class="card-body gap-3 p-4">
                <div class="flex flex-wrap items-center justify-between gap-3">
                  <div class="flex items-start gap-3">
                    <Globe class="mt-0.5 size-5 shrink-0 text-primary" />
                    <div>
                      <div class="text-sm font-medium">MangaDex</div>
                      <div class="text-xs text-base-content/60">
                        <template v-if="sync.syncing">Checking for new chapters…</template>
                        <template v-else>
                          Last synced {{ sync.lastSync }} · {{ sync.newChapters }} new chapters · auto every
                          {{ sync.autoEvery }}
                        </template>
                      </div>
                    </div>
                  </div>
                  <button class="btn btn-primary btn-sm gap-2" :disabled="sync.syncing" @click="syncNow">
                    <RefreshCw class="size-4" :class="{ 'animate-spin': sync.syncing }" />
                    {{ sync.syncing ? "Syncing…" : "Sync now" }}
                  </button>
                </div>
              </div>
            </div>
          </section>

          <section class="flex flex-col gap-3">
            <div class="flex items-center justify-between gap-2">
              <h3 class="text-xs font-semibold uppercase tracking-wide text-base-content/50">Downloads</h3>
              <button class="btn btn-ghost btn-sm" :disabled="!hasDone" @click="clearDone">Clear completed</button>
            </div>
            <div class="flex flex-col gap-1.5">
              <div
                v-for="d in dl"
                :key="d.id"
                class="flex items-center gap-3 rounded-box surface-border bg-base-100 p-2.5"
              >
                <img :src="d.series.coverUrl" :alt="d.series.title" class="cover h-12 shrink-0 rounded object-cover" />
                <div class="min-w-0 grow">
                  <div class="flex items-center gap-2">
                    <span class="truncate text-sm font-medium">{{ d.series.title }}</span>
                    <span class="shrink-0 text-xs text-base-content/60">{{ d.chapter }}</span>
                  </div>
                  <div class="mt-1 flex items-center gap-2 text-xs">
                    <span class="badge badge-sm" :class="dlBadge[d.status]">
                      {{ d.status === "downloading" ? `Downloading ${d.progress}%` : dlLabel[d.status] }}
                    </span>
                    <span class="text-base-content/50">{{ d.size }}</span>
                  </div>
                  <progress
                    v-if="d.status === 'downloading' || d.status === 'paused'"
                    class="progress progress-primary mt-1.5 h-1"
                    :value="d.progress"
                    max="100"
                  ></progress>
                </div>
                <div class="flex shrink-0 items-center gap-1">
                  <button
                    v-if="d.status === 'downloading'"
                    class="btn btn-square btn-ghost btn-xs"
                    aria-label="Pause"
                    @click="d.status = 'paused'"
                  >
                    <Pause class="size-4" />
                  </button>
                  <button
                    v-else-if="d.status === 'paused'"
                    class="btn btn-square btn-ghost btn-xs"
                    aria-label="Resume"
                    @click="d.status = 'downloading'"
                  >
                    <Play class="size-4" />
                  </button>
                  <button
                    v-else-if="d.status === 'failed'"
                    class="btn btn-square btn-ghost btn-xs"
                    aria-label="Retry"
                    @click="retryDownload(d)"
                  >
                    <RefreshCw class="size-4" />
                  </button>
                  <button class="btn btn-square btn-ghost btn-xs" aria-label="Remove" @click="removeDownload(d)">
                    <X class="size-4" />
                  </button>
                </div>
              </div>
              <p v-if="!dl.length" class="py-8 text-center text-sm text-base-content/50">No downloads.</p>
            </div>
          </section>
        </div>

        <div v-else-if="active === 'about'" key="about" class="flex flex-col gap-6">
          <!-- Brand -->
          <div class="card bg-base-100">
            <div class="card-body gap-4 p-5">
              <div class="flex flex-wrap items-center gap-4">
                <div class="flex size-14 shrink-0 items-center justify-center rounded-box bg-primary/10 text-primary">
                  <Cherry class="size-8" />
                </div>
                <div class="min-w-0 grow">
                  <div class="flex flex-wrap items-center gap-2">
                    <h2 class="text-2xl font-bold">lychee</h2>
                    <span class="badge badge-primary badge-sm">v{{ about.version }}</span>
                  </div>
                  <p class="text-sm text-base-content/60">Self-hosted manga, comic &amp; art-gallery server.</p>
                </div>
                <div class="flex flex-col items-end gap-1.5">
                  <span class="flex items-center gap-1.5 text-xs font-medium text-success">
                    <Check class="size-4" />Up to date
                  </span>
                  <button class="btn btn-ghost btn-sm gap-2 surface-border">
                    <RefreshCw class="size-4" />Check for updates
                  </button>
                </div>
              </div>
              <div class="divider my-0"></div>
              <div class="flex flex-wrap gap-2">
                <a class="btn btn-ghost btn-sm gap-2 surface-border" href="#"><Github class="size-4" />GitHub</a>
                <a class="btn btn-ghost btn-sm gap-2 surface-border" href="#"><BookText class="size-4" />Docs</a>
                <a class="btn btn-ghost btn-sm gap-2 surface-border" href="#"><Bug class="size-4" />Report an issue</a>
              </div>
            </div>
          </div>

          <!-- Library at a glance -->
          <section class="flex flex-col gap-3">
            <h3 class="text-xs font-semibold uppercase tracking-wide text-base-content/50">Library</h3>
            <div class="stats stats-vertical w-full surface-border bg-base-100 sm:stats-horizontal">
              <div v-for="s in libStats" :key="s.label" class="stat">
                <div class="stat-title">{{ s.label }}</div>
                <div class="stat-value text-2xl">{{ s.value }}</div>
              </div>
            </div>
          </section>

          <!-- Server -->
          <section class="flex flex-col gap-3">
            <h3 class="text-xs font-semibold uppercase tracking-wide text-base-content/50">Server</h3>
            <div class="card bg-base-100">
              <div class="card-body p-4">
                <dl class="grid grid-cols-1 gap-x-8 gap-y-3 text-sm sm:grid-cols-2">
                  <div v-for="row in serverInfo" :key="row.label" class="flex items-center justify-between gap-4">
                    <dt class="text-base-content/50">{{ row.label }}</dt>
                    <dd class="font-medium">{{ row.value }}</dd>
                  </div>
                </dl>
              </div>
            </div>
          </section>
        </div>
        </Transition>
      </div>
    </div>
  </div>
</template>
