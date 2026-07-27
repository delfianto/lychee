<script setup lang="ts">
// Settings → Accounts: connect/disconnect the MangaDex account (with "Sync") and the
// reading trackers (AniList, MyAnimeList, MangaUpdates), each via a popup.
// Trackers with no public API (NovelUpdates) are hidden.
import { Link2, RefreshCw } from "lucide-vue-next";
import { onMounted, onUnmounted, ref } from "vue";

import { onTaskDone } from "../../api/events";
import {
  disconnectProvider,
  disconnectTracker,
  fetchProviders,
  fetchTrackers,
  setTrackerSyncOnRead,
  syncProvider,
} from "../../api/settingsQueries";
import { toast } from "../../lib/toast";
import MangaDexConnectModal from "./MangaDexConnectModal.vue";
import TrackerConnectModal from "./TrackerConnectModal.vue";

interface AccountRow {
  id: string;
  name: string;
  kind: "provider" | "tracker";
  connected: boolean;
  accountName: string;
  syncOnRead: boolean;
  authKind: string;
}

const accounts = ref<AccountRow[]>([]);
const trackerTarget = ref<AccountRow | null>(null);
const mangadexOpen = ref(false);

async function load(): Promise<void> {
  const [providers, trackers] = await Promise.all([fetchProviders(), fetchTrackers()]);
  const rows: AccountRow[] = [];
  const md = providers.find((p) => p.id === "mangadex");
  if (md) {
    rows.push({
      id: md.id, name: md.name, kind: "provider",
      connected: md.connected, accountName: md.accountName ?? "", syncOnRead: false, authKind: "",
    });
  }
  for (const t of trackers) {
    if (t.authKind === "unsupported") continue; // hide trackers with no public API (NovelUpdates)
    rows.push({
      id: t.id, name: t.name, kind: "tracker",
      connected: t.connected, accountName: t.accountName ?? "", syncOnRead: t.syncOnRead, authKind: t.authKind,
    });
  }
  accounts.value = rows;
}

function connect(a: AccountRow): void {
  if (a.kind === "provider") mangadexOpen.value = true;
  else trackerTarget.value = a;
}
async function disconnect(a: AccountRow): Promise<void> {
  if (a.kind === "provider") await disconnectProvider(a.id);
  else await disconnectTracker(a.id);
  await load();
  toast(`${a.name} disconnected`, "info");
}
async function onTrackerConnected(): Promise<void> {
  const name = trackerTarget.value?.name;
  trackerTarget.value = null;
  await load();
  if (name) toast(`${name} connected`);
}
async function onMangadexConnected(): Promise<void> {
  mangadexOpen.value = false;
  await load();
  toast("MangaDex account connected");
}
async function setSyncOnRead(a: AccountRow): Promise<void> {
  await setTrackerSyncOnRead(a.id, a.syncOnRead);
}
function syncAccount(a: AccountRow): void {
  void syncProvider(a.id);
  toast("Syncing your MangaDex account…");
}

const disposeDone = onTaskDone((task) => {
  if (task.kind === "import" && task.status === "done") {
    toast(`Synced ${(task.result?.synced as number) ?? 0} series`);
  }
});
onUnmounted(disposeDone);
onMounted(load);
</script>

<template>
  <section class="flex flex-col gap-3">
    <h3 class="text-xs font-semibold uppercase tracking-wide text-base-content/50">Accounts</h3>
    <div class="card grow bg-base-100">
      <div class="card-body gap-4 p-4">
        <div v-for="a in accounts" :key="a.id" class="flex flex-wrap items-center justify-between gap-4">
          <div class="flex items-start gap-3">
            <Link2 class="mt-0.5 size-5 shrink-0 text-primary" />
            <div>
              <div class="text-sm font-medium">{{ a.name }}</div>
              <div class="text-xs" :class="a.connected ? 'text-success' : 'text-base-content/50'">
                {{ a.connected ? (a.accountName ? `Connected as ${a.accountName}` : "Connected") : "Not connected" }}
              </div>
            </div>
          </div>
          <div class="flex items-center gap-2">
            <label v-if="a.connected && a.kind === 'tracker'" class="flex items-center gap-2 text-xs text-base-content/60">
              Sync on read
              <input v-model="a.syncOnRead" type="checkbox" class="toggle toggle-primary toggle-sm" @change="setSyncOnRead(a)" />
            </label>
            <button v-if="a.connected && a.kind === 'provider'" class="btn btn-primary btn-sm gap-1" @click="syncAccount(a)">
              <RefreshCw class="size-4" />Sync
            </button>
            <button v-if="a.connected" class="btn btn-ghost btn-sm text-error" @click="disconnect(a)">Disconnect</button>
            <button v-else class="btn btn-primary btn-sm" @click="connect(a)">Connect</button>
          </div>
        </div>
      </div>
    </div>

    <TrackerConnectModal
      v-if="trackerTarget"
      :tracker="trackerTarget"
      @close="trackerTarget = null"
      @connected="onTrackerConnected"
    />
    <MangaDexConnectModal
      v-if="mangadexOpen"
      @close="mangadexOpen = false"
      @connected="onMangadexConnected"
    />
  </section>
</template>
