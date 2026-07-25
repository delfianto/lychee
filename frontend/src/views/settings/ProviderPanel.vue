<script setup lang="ts">
// Settings → Metadata provider (MangaDex): config toggles + the OAuth account
// (connect / import follows / disconnect). Owns the import SSE result toast.
import { Check, Download, Globe, Image, Languages, Link2, Wand2 } from "lucide-vue-next";
import { onMounted, onUnmounted, reactive, ref, watch } from "vue";

import { api } from "../../api/client";
import { onTaskDone } from "../../api/events";
import { toast } from "../../lib/toast";

const provider = reactive({ id: "mangadex", enabled: true, language: "en", autoMatch: true, fetchCovers: true, dataSaver: false });
const providerLanguages = ["en", "ja", "ko", "zh"];
let providerLoaded = false;
// MangaDex account (OAuth) state + the one-time connect form.
const account = reactive({ connected: false, name: "" });
const connectForm = reactive({ clientId: "", clientSecret: "", username: "", password: "" });
const connecting = ref(false);
async function loadProvider(): Promise<void> {
  const { data } = await api.GET("/api/providers");
  const md = (data ?? []).find((p) => p.id === "mangadex") ?? (data ?? [])[0];
  if (md) {
    provider.id = md.id;
    provider.enabled = md.enabled;
    provider.language = md.language;
    provider.autoMatch = md.autoMatch;
    provider.fetchCovers = md.fetchCovers;
    provider.dataSaver = md.dataSaver;
    account.connected = md.connected;
    account.name = md.accountName ?? "";
  }
}
async function connectAccount(): Promise<void> {
  connecting.value = true;
  const { error } = await api.POST("/api/providers/{provider_id}/connect", {
    params: { path: { provider_id: provider.id } },
    body: { ...connectForm },
  });
  connecting.value = false;
  if (error) {
    toast("Connect failed — check credentials & LYCHEE_SECRET_KEY", "error");
    return;
  }
  Object.assign(connectForm, { clientId: "", clientSecret: "", username: "", password: "" });
  await loadProvider();
  toast("MangaDex account connected");
}
async function disconnectAccount(): Promise<void> {
  await api.POST("/api/providers/{provider_id}/disconnect", { params: { path: { provider_id: provider.id } } });
  await loadProvider();
  toast("Disconnected", "info");
}
async function importFollows(): Promise<void> {
  await api.POST("/api/providers/{provider_id}/import", { params: { path: { provider_id: provider.id } } });
  toast("Importing your MangaDex follows…");
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
        dataSaver: provider.dataSaver,
      },
    });
  },
);

const disposeDone = onTaskDone((task) => {
  if (task.kind === "import" && task.status === "done") {
    toast(`Imported ${(task.result?.imported as number) ?? 0} series`);
  }
});
onUnmounted(disposeDone);
onMounted(async () => {
  await loadProvider();
  providerLoaded = true;
});
</script>

<template>
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
        <label class="flex items-center justify-between gap-4">
          <div class="flex items-start gap-3">
            <Download class="mt-0.5 size-5 shrink-0 text-primary" />
            <div>
              <div class="text-sm font-medium">Data saver</div>
              <div class="text-xs text-base-content/50">Download smaller, compressed pages instead of original quality</div>
            </div>
          </div>
          <input v-model="provider.dataSaver" type="checkbox" class="toggle toggle-primary toggle-sm" />
        </label>

        <!-- MangaDex account (OAuth) -->
        <div class="divider my-1 text-xs text-base-content/40">Account</div>
        <div v-if="account.connected" class="flex flex-wrap items-center justify-between gap-3">
          <div class="flex items-center gap-2 text-sm">
            <Check class="size-4 text-success" />
            Connected as <span class="font-medium">{{ account.name || "MangaDex user" }}</span>
          </div>
          <div class="flex gap-2">
            <button class="btn btn-primary btn-sm gap-1" @click="importFollows">
              <Download class="size-4" />Import follows
            </button>
            <button class="btn btn-ghost btn-sm" @click="disconnectAccount">Disconnect</button>
          </div>
        </div>
        <div v-else class="flex flex-col gap-2">
          <p class="text-xs text-base-content/50">
            Connect a MangaDex
            <a href="https://mangadex.org/settings" target="_blank" class="link" rel="noopener">personal API client</a>
            to import your follows &amp; reading status. Secrets are encrypted at rest.
          </p>
          <div class="grid gap-2 sm:grid-cols-2">
            <input v-model="connectForm.clientId" class="input input-bordered input-sm" placeholder="Client ID" />
            <input v-model="connectForm.clientSecret" type="password" class="input input-bordered input-sm" placeholder="Client secret" />
            <input v-model="connectForm.username" class="input input-bordered input-sm" placeholder="Username" />
            <input v-model="connectForm.password" type="password" class="input input-bordered input-sm" placeholder="Password" />
          </div>
          <button
            class="btn btn-primary btn-sm self-start gap-1"
            :disabled="connecting || !connectForm.clientId || !connectForm.password"
            @click="connectAccount"
          >
            <Link2 class="size-4" />{{ connecting ? "Connecting…" : "Connect" }}
          </button>
        </div>
      </div>
    </div>
  </section>
</template>
