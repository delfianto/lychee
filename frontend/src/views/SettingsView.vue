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
import { type Component, computed, onMounted, onUnmounted, reactive, ref, watch } from "vue";

import { api } from "../api/client";
import { activeTasks, onTaskDone } from "../api/events";
import { relativeTime } from "../api/format";
import { fetchDashboard, fetchLibrarySummaries } from "../api/queries";
import SegmentedToggle from "../components/SegmentedToggle.vue";
import { toast } from "../lib/toast";
import { type ReaderSettings, useReaderSettings } from "../lib/readerSettings";
import { THEMES, type Mode, useTheme } from "../lib/theme";

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
  system: boolean;
}
const CAT_LABEL: Record<string, string> = {
  genre: "Genre",
  theme: "Theme",
  content: "Content",
  format: "Format",
  content_rating: "Content Rating",
  demographic: "Demographic",
};
// Galleries are few and the table filters/paginates client-side, so load all rows once.
const taxonomy = ref<TaxRow[]>([]);
async function loadTaxonomy(): Promise<void> {
  const { data } = await api.GET("/api/taxonomy", { params: { query: { pageSize: 500 } } });
  taxonomy.value = (data?.items ?? []).map((t) => ({
    id: t.id,
    name: t.name,
    category: CAT_LABEL[t.category] ?? t.category,
    uses: t.uses,
    enabled: t.enabled,
    system: t.system,
  }));
}
const taxCategories = computed(() => [...new Set(taxonomy.value.map((r) => r.category))].sort());
const taxSearch = ref("");
const taxCat = ref("");
const taxPage = ref(0);
const TAX_PAGE_SIZE = 20;
const taxFiltered = computed(() => {
  const q = taxSearch.value.trim().toLowerCase();
  return taxonomy.value.filter(
    (r) => (!q || r.name.toLowerCase().includes(q)) && (!taxCat.value || r.category === taxCat.value),
  );
});
const taxPageCount = computed(() => Math.max(1, Math.ceil(taxFiltered.value.length / TAX_PAGE_SIZE)));
const taxRows = computed(() =>
  taxFiltered.value.slice(taxPage.value * TAX_PAGE_SIZE, taxPage.value * TAX_PAGE_SIZE + TAX_PAGE_SIZE),
);
watch([taxSearch, taxCat], () => (taxPage.value = 0));
async function toggleTax(row: TaxRow): Promise<void> {
  await api.PATCH("/api/taxonomy/{tag_id}", {
    params: { path: { tag_id: row.id } },
    body: { enabled: row.enabled },
  });
}
async function addTax(): Promise<void> {
  const name = window.prompt("New tag name?");
  if (!name?.trim()) return;
  const { data } = await api.POST("/api/taxonomy", {
    body: { name: name.trim(), category: "genre" },
  });
  if (data) {
    taxonomy.value.push({
      id: data.id,
      name: data.name,
      category: CAT_LABEL[data.category] ?? data.category,
      uses: data.uses,
      enabled: data.enabled,
      system: data.system,
    });
    toast(`Added “${data.name}”`);
  }
}
async function removeTax(row: TaxRow): Promise<void> {
  await api.DELETE("/api/taxonomy/{tag_id}", { params: { path: { tag_id: row.id } } });
  taxonomy.value = taxonomy.value.filter((r) => r.id !== row.id);
}

// --- Downloads + MangaDex sync ---
interface DlRow {
  id: string;
  series: { coverUrl: string; title: string };
  chapter: string;
  status: string;
  progress: number;
  size: string;
}
const dl = ref<DlRow[]>([]);
const sync = reactive({ lastSync: "never", newChapters: 0, autoEvery: "6h", syncing: false });
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
const hasDone = computed(() => dl.value.some((d) => d.status === "done"));
function formatBytes(n: number | null | undefined): string {
  if (!n) return "—";
  return n >= 1e6 ? `${(n / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1e3))} KB`;
}
async function loadDownloads(): Promise<void> {
  const { data } = await api.GET("/api/downloads");
  dl.value = (data ?? []).map((d) => ({
    id: d.id,
    series: { coverUrl: d.series.coverUrl, title: d.series.title },
    chapter: d.chapter,
    status: d.status,
    progress: d.progress,
    size: formatBytes(d.sizeBytes),
  }));
}
async function loadSync(): Promise<void> {
  const { data } = await api.GET("/api/sync");
  if (!data) return;
  sync.lastSync = data.lastSync ? relativeTime(data.lastSync) : "never";
  sync.newChapters = data.newChapters;
  sync.autoEvery = `${Math.max(1, Math.round(data.autoEveryMinutes / 60))}h`;
}
async function syncNow(): Promise<void> {
  sync.syncing = true;
  const { data } = await api.POST("/api/sync");
  if (data) {
    sync.lastSync = data.lastSync ? relativeTime(data.lastSync) : "just now";
    sync.newChapters = data.newChapters;
  }
  sync.syncing = false;
}
async function retryDownload(d: DlRow): Promise<void> {
  await api.POST("/api/downloads/{task_id}/retry", { params: { path: { task_id: d.id } } });
  toast("Download queued"); // the list refreshes when the download.done event arrives
}
async function removeDownload(d: DlRow): Promise<void> {
  await api.DELETE("/api/downloads/{task_id}", { params: { path: { task_id: d.id } } });
  await loadDownloads();
}
async function clearDone(): Promise<void> {
  await api.POST("/api/downloads/clear-completed");
  await loadDownloads();
}

// --- Libraries ---
interface LibraryRow {
  id: string;
  name: string;
  path: string;
  series: number;
  lastScan: string;
}
const libraries = ref<LibraryRow[]>([]);
// A scan runs in the background; disable the triggers while one is in flight.
const scanning = computed(() => activeTasks.value.some((t) => t.kind === "scan"));
async function loadLibraries(): Promise<void> {
  const { data } = await api.GET("/api/libraries");
  libraries.value = (data ?? []).map((l) => ({
    id: l.id,
    name: l.name,
    path: l.path,
    series: l.seriesCount,
    lastScan: l.lastScan ? relativeTime(l.lastScan) : "never",
  }));
}
async function scanAll(): Promise<void> {
  await api.POST("/api/libraries/scan");
  toast("Scan started"); // libraries refresh when the scan.done event arrives
}
async function scanOne(id: string): Promise<void> {
  await api.POST("/api/libraries/{library_id}/scan", { params: { path: { library_id: id } } });
  toast("Scan started");
}
async function removeLibrary(id: string): Promise<void> {
  await api.DELETE("/api/libraries/{library_id}", { params: { path: { library_id: id } } });
  await loadLibraries();
}
async function addLibrary(): Promise<void> {
  const name = window.prompt("Library name?");
  if (!name?.trim()) return;
  const path = window.prompt("Library path (a folder on the server)?");
  if (!path?.trim()) return;
  await api.POST("/api/libraries", { body: { name: name.trim(), path: path.trim(), kind: "manga" } });
  await loadLibraries();
}

// --- Metadata provider (MangaDex) ---
const provider = reactive({ id: "mangadex", enabled: true, language: "en", autoMatch: true, fetchCovers: true });
const providerLanguages = ["en", "ja", "ko", "zh"];
let providerLoaded = false;
async function loadProvider(): Promise<void> {
  const { data } = await api.GET("/api/providers");
  const md = (data ?? []).find((p) => p.id === "mangadex") ?? (data ?? [])[0];
  if (md) {
    provider.id = md.id;
    provider.enabled = md.enabled;
    provider.language = md.language;
    provider.autoMatch = md.autoMatch;
    provider.fetchCovers = md.fetchCovers;
  }
}
watch(
  () => ({ ...provider }),
  () => {
    if (!providerLoaded) return;
    void api.PATCH("/api/providers/{provider_id}", {
      params: { path: { provider_id: provider.id } },
      body: {
        enabled: provider.enabled,
        language: provider.language,
        autoMatch: provider.autoMatch,
        fetchCovers: provider.fetchCovers,
      },
    });
  },
);

// --- Trackers ---
interface TrackerRow {
  id: string;
  name: string;
  connected: boolean;
  syncOnRead: boolean;
}
const trackers = ref<TrackerRow[]>([]);
async function loadTrackers(): Promise<void> {
  const { data } = await api.GET("/api/trackers");
  trackers.value = (data ?? []).map((t) => ({
    id: t.id,
    name: t.name,
    connected: t.connected,
    syncOnRead: t.syncOnRead,
  }));
}
async function toggleTracker(t: TrackerRow): Promise<void> {
  if (t.connected) {
    await api.DELETE("/api/trackers/{tracker_id}", { params: { path: { tracker_id: t.id } } });
    t.connected = false;
  } else {
    const { data } = await api.POST("/api/trackers/{tracker_id}/connect", {
      params: { path: { tracker_id: t.id } },
    });
    if (data) t.connected = data.connected;
  }
}
async function setSyncOnRead(t: TrackerRow): Promise<void> {
  await api.PATCH("/api/trackers/{tracker_id}", {
    params: { path: { tracker_id: t.id } },
    body: { syncOnRead: t.syncOnRead },
  });
}

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

// --- About ---
const about = reactive({ version: "0.0.0", platform: "", database: "", uptime: "", started: "" });
const libStats = ref<{ label: string; value: string }[]>([]);
const serverInfo = computed(() => [
  { label: "Version", value: about.version },
  { label: "Platform", value: about.platform },
  { label: "Database", value: about.database },
  { label: "Uptime", value: about.uptime },
  { label: "Started", value: about.started },
]);
function formatUptime(seconds: number): string {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  return days > 0 ? `${days}d ${hours}h` : `${hours}h ${Math.floor((seconds % 3600) / 60)}m`;
}
async function loadAbout(): Promise<void> {
  const { data } = await api.GET("/api/about");
  if (data) {
    about.version = data.version;
    about.platform = data.platform;
    about.database = data.database;
    about.uptime = formatUptime(data.uptimeSeconds);
    about.started = new Date(data.started).toLocaleDateString();
  }
  const [dashboard, summaries] = await Promise.all([fetchDashboard(), fetchLibrarySummaries()]);
  const storage = summaries.reduce((n, s) => n + s.sizeGb, 0);
  libStats.value = [
    { label: "Series", value: dashboard.stats.series.toLocaleString() },
    { label: "Unread", value: dashboard.stats.unreadChapters.toLocaleString() },
    { label: "Reading", value: dashboard.stats.reading.toLocaleString() },
    { label: "Storage", value: `${storage.toFixed(1)} GB` },
  ];
}

// Refetch the affected list when a background scan/download finishes (SSE).
const disposeTaskListener = onTaskDone((task) => {
  if (task.kind === "scan") {
    void loadLibraries();
    toast(
      task.status === "done" ? "Scan complete" : "Scan failed",
      task.status === "done" ? "success" : "error",
    );
  } else if (task.kind === "download") {
    void loadDownloads();
  }
});
onUnmounted(disposeTaskListener);

onMounted(async () => {
  await Promise.all([
    loadLibraries(),
    loadProvider(),
    loadTrackers(),
    loadTaxonomy(),
    loadDownloads(),
    loadSync(),
    loadAbout(),
  ]);
  providerLoaded = true;
});
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
                <button class="btn btn-ghost btn-sm gap-1" :disabled="scanning" @click="scanAll">
                  <RefreshCw :class="['size-4', scanning && 'animate-spin']" />Scan all
                </button>
                <button class="btn btn-primary btn-sm gap-1" @click="addLibrary"><Plus class="size-4" />Add library</button>
              </div>
            </div>
            <div class="grid gap-4 lg:grid-cols-2">
              <div v-for="lib in libraries" :key="lib.id" class="card bg-base-100">
                <div class="card-body flex-row flex-wrap items-center gap-4 p-4">
                  <Library class="size-5 shrink-0 text-primary" />
                  <div class="min-w-0 grow">
                    <div class="font-medium">{{ lib.name }}</div>
                    <div class="truncate font-mono text-xs text-base-content/60">{{ lib.path }}</div>
                    <div class="text-xs text-base-content/50">{{ lib.series }} series · scanned {{ lib.lastScan }}</div>
                  </div>
                  <button class="btn btn-ghost btn-sm" :disabled="scanning" @click="scanOne(lib.id)">Scan</button>
                  <button class="btn btn-ghost btn-sm text-error" @click="removeLibrary(lib.id)">Remove</button>
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
                  <div v-for="t in trackers" :key="t.id" class="flex flex-wrap items-center justify-between gap-4">
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
                        <input v-model="t.syncOnRead" type="checkbox" class="toggle toggle-primary toggle-sm" @change="setSyncOnRead(t)" />
                      </label>
                      <button
                        class="btn btn-sm"
                        :class="t.connected ? 'btn-ghost text-error' : 'btn-primary'"
                        @click="toggleTracker(t)"
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
            <button class="btn btn-primary btn-sm gap-1" @click="addTax"><Plus class="size-4" />Add</button>
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
                        <input v-model="row.enabled" type="checkbox" class="toggle toggle-primary toggle-sm" @change="toggleTax(row)" />
                      </td>
                      <td class="whitespace-nowrap text-right">
                        <button class="btn btn-ghost btn-xs text-error" :disabled="row.system" @click="removeTax(row)">Delete</button>
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
