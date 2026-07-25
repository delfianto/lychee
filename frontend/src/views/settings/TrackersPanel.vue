<script setup lang="ts">
// Settings → Trackers: connect/disconnect reading trackers (AniList, MyAnimeList,
// MangaUpdates) and toggle sync-on-read. The connect flow lives in the child modal.
import { Link2 } from "lucide-vue-next";
import { onMounted, ref } from "vue";

import { api } from "../../api/client";
import { toast } from "../../lib/toast";
import TrackerConnectModal from "./TrackerConnectModal.vue";

interface TrackerRow {
  id: string;
  name: string;
  connected: boolean;
  syncOnRead: boolean;
  authKind: string;
}
const trackers = ref<TrackerRow[]>([]);
const connectTarget = ref<TrackerRow | null>(null);

async function loadTrackers(): Promise<void> {
  const { data } = await api.GET("/api/trackers");
  trackers.value = (data ?? []).map((t) => ({
    id: t.id,
    name: t.name,
    connected: t.connected,
    syncOnRead: t.syncOnRead,
    authKind: t.authKind,
  }));
}
async function toggleTracker(t: TrackerRow): Promise<void> {
  if (t.connected) {
    await api.DELETE("/api/trackers/{tracker_id}", { params: { path: { tracker_id: t.id } } });
    await loadTrackers();
    toast(`${t.name} disconnected`, "info");
  } else if (t.authKind === "unsupported") {
    toast(`${t.name} has no public API`, "info");
  } else {
    connectTarget.value = t;
  }
}
async function onConnected(): Promise<void> {
  const name = connectTarget.value?.name;
  connectTarget.value = null;
  await loadTrackers();
  if (name) toast(`${name} connected`);
}
async function setSyncOnRead(t: TrackerRow): Promise<void> {
  await api.PATCH("/api/trackers/{tracker_id}", {
    params: { path: { tracker_id: t.id } },
    body: { syncOnRead: t.syncOnRead },
  });
}

onMounted(loadTrackers);
</script>

<template>
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

    <TrackerConnectModal
      v-if="connectTarget"
      :tracker="connectTarget"
      @close="connectTarget = null"
      @connected="onConnected"
    />
  </section>
</template>
