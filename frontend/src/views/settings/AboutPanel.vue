<script setup lang="ts">
// Settings → About: version/platform/uptime + a library-at-a-glance summary.
import { Cherry } from "lucide-vue-next";
import { computed, onMounted, reactive, ref } from "vue";

import { fetchDashboard, fetchLibrarySummaries } from "../../api/queries";
import { fetchAbout } from "../../api/settingsQueries";

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
  const data = await fetchAbout();
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

onMounted(loadAbout);
</script>

<template>
  <div class="flex flex-col gap-6">
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
</template>
