<script setup lang="ts">
// Settings → Metadata provider (MangaDex) config toggles. The account (connect /
// import follows / disconnect) lives in the Accounts panel alongside the trackers.
import { Download, Globe, Image, Languages, Wand2 } from "lucide-vue-next";
import { onMounted, reactive, watch } from "vue";

import { api } from "../../api/client";

const provider = reactive({ id: "mangadex", enabled: true, language: "en", autoMatch: true, fetchCovers: true, dataSaver: false });
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
    provider.dataSaver = md.dataSaver;
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
        dataSaver: provider.dataSaver,
      },
    });
  },
);

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
      </div>
    </div>
  </section>
</template>
