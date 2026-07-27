<script setup lang="ts">
// The tracker connect dialog. OAuth trackers do client-creds → authorize URL →
// paste code; credentials trackers (MangaUpdates) do a one-step username/password
// login. Emits `connected` on success (parent reloads + closes).
import { Link2, X } from "lucide-vue-next";
import { reactive } from "vue";

import { api } from "../../api/client";
import { toast } from "../../lib/toast";

const props = defineProps<{ tracker: { id: string; name: string; authKind: string } }>();
const emit = defineEmits<{ close: []; connected: [] }>();

const form = reactive({
  clientId: "", clientSecret: "", redirectUri: window.location.origin,
  authorizeUrl: "", code: "", username: "", password: "", busy: false,
});

async function beginTrackerAuth(): Promise<void> {
  form.busy = true;
  const { data, error } = await api.POST("/api/trackers/{tracker_id}/connect", {
    params: { path: { tracker_id: props.tracker.id } },
    body: { clientId: form.clientId, clientSecret: form.clientSecret, redirectUri: form.redirectUri },
  });
  form.busy = false;
  if (error || !data) {
    toast("Couldn't start auth — check credentials & LYCHEE_SECRET_KEY", "error");
    return;
  }
  form.authorizeUrl = data.authorizeUrl;
}
async function completeTrackerAuth(): Promise<void> {
  form.busy = true;
  // The state nonce rides in the authorize URL we were just handed (embedded by the
  // backend's TrackerAuthUrl response) — round-trip it invisibly rather than asking
  // the user to also paste it; the backend verifies it matches what it generated.
  const state = new URL(form.authorizeUrl).searchParams.get("state") ?? "";
  const { error } = await api.POST("/api/trackers/{tracker_id}/callback", {
    params: { path: { tracker_id: props.tracker.id } },
    body: { code: form.code.trim(), redirectUri: form.redirectUri, state },
  });
  form.busy = false;
  if (error) {
    toast("Authorization failed — is the code correct?", "error");
    return;
  }
  emit("connected");
}
async function loginTracker(): Promise<void> {
  form.busy = true;
  const { error } = await api.POST("/api/trackers/{tracker_id}/login", {
    params: { path: { tracker_id: props.tracker.id } },
    body: { username: form.username, password: form.password },
  });
  form.busy = false;
  if (error) {
    toast("Login failed — check credentials & LYCHEE_SECRET_KEY", "error");
    return;
  }
  emit("connected");
}
</script>

<template>
  <div class="modal modal-open" @click.self="emit('close')">
    <div class="modal-box">
      <div class="mb-3 flex items-center justify-between">
        <h3 class="text-lg font-bold">Connect {{ tracker.name }}</h3>
        <button class="btn btn-circle btn-ghost btn-sm" aria-label="Close" @click="emit('close')">
          <X class="size-4" />
        </button>
      </div>

      <!-- Credentials trackers (MangaUpdates): one-step username/password login -->
      <div v-if="tracker.authKind === 'credentials'" class="flex flex-col gap-2">
        <p class="mb-1 text-xs text-base-content/50">
          Sign in with your {{ tracker.name }} account. Your session token is encrypted at rest.
        </p>
        <input v-model="form.username" class="input input-bordered input-sm" placeholder="Username" />
        <input v-model="form.password" type="password" class="input input-bordered input-sm" placeholder="Password" />
        <button
          class="btn btn-primary btn-sm self-start"
          :disabled="form.busy || !form.username || !form.password"
          @click="loginTracker"
        >
          {{ form.busy ? "Signing in…" : "Sign in" }}
        </button>
      </div>

      <!-- OAuth trackers (AniList, MyAnimeList): client creds → authorize → code -->
      <div v-else class="flex flex-col gap-2">
        <p class="mb-1 text-xs text-base-content/50">
          Create an OAuth client on {{ tracker.name }} with the redirect URI below, then paste its
          client ID &amp; secret. Secrets are encrypted at rest.
        </p>
        <input v-model="form.clientId" class="input input-bordered input-sm" placeholder="Client ID" />
        <input v-model="form.clientSecret" type="password" class="input input-bordered input-sm" placeholder="Client secret" />
        <input v-model="form.redirectUri" class="input input-bordered input-sm" placeholder="Redirect URI" />
        <button
          v-if="!form.authorizeUrl"
          class="btn btn-primary btn-sm self-start"
          :disabled="form.busy || !form.clientId || !form.clientSecret"
          @click="beginTrackerAuth"
        >
          {{ form.busy ? "Working…" : "Get authorize link" }}
        </button>
        <template v-else>
          <a :href="form.authorizeUrl" target="_blank" rel="noopener" class="btn btn-outline btn-sm gap-1">
            <Link2 class="size-4" />Authorize on {{ tracker.name }} ↗
          </a>
          <p class="text-xs text-base-content/50">After authorizing, paste the <code>code</code> from the redirect URL:</p>
          <div class="flex gap-2">
            <input v-model="form.code" class="input input-bordered input-sm grow" placeholder="Authorization code" />
            <button
              class="btn btn-primary btn-sm"
              :disabled="form.busy || !form.code"
              @click="completeTrackerAuth"
            >
              Complete
            </button>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>
