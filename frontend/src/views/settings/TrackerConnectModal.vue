<script setup lang="ts">
// The tracker connect dialog. OAuth trackers do client-creds → authorize URL →
// paste code; credentials trackers (MangaUpdates) do a one-step username/password
// login. Emits `connected` on success (parent reloads + closes).
import { Link2, X } from "lucide-vue-next";
import { reactive, ref } from "vue";

import { beginTrackerConnect, completeTrackerConnect, loginTracker } from "../../api/settingsQueries";
import { useFocusTrap } from "../../lib/focusTrap";
import { toast } from "../../lib/toast";

const props = defineProps<{ tracker: { id: string; name: string; authKind: string } }>();
const emit = defineEmits<{ close: []; connected: [] }>();

// No `open` prop — the parent mounts this component only while shown.
const modalBox = ref<HTMLElement | null>(null);
useFocusTrap(modalBox, ref(true));

const form = reactive({
  clientId: "", clientSecret: "", redirectUri: window.location.origin,
  authorizeUrl: "", code: "", username: "", password: "", busy: false,
});

async function beginTrackerAuth(): Promise<void> {
  form.busy = true;
  try {
    form.authorizeUrl = await beginTrackerConnect(props.tracker.id, {
      clientId: form.clientId,
      clientSecret: form.clientSecret,
      redirectUri: form.redirectUri,
    });
  } catch (e) {
    toast(e instanceof Error ? e.message : "Couldn't start auth", "error");
  } finally {
    form.busy = false;
  }
}
async function completeTrackerAuth(): Promise<void> {
  form.busy = true;
  // The state nonce rides in the authorize URL we were just handed (embedded by the
  // backend's TrackerAuthUrl response) — round-trip it invisibly rather than asking
  // the user to also paste it; the backend verifies it matches what it generated.
  const state = new URL(form.authorizeUrl).searchParams.get("state") ?? "";
  try {
    await completeTrackerConnect(props.tracker.id, { code: form.code.trim(), redirectUri: form.redirectUri, state });
  } catch (e) {
    form.busy = false;
    toast(e instanceof Error ? e.message : "Authorization failed", "error");
    return;
  }
  form.busy = false;
  emit("connected");
}
async function loginTrackerAccount(): Promise<void> {
  form.busy = true;
  try {
    await loginTracker(props.tracker.id, { username: form.username, password: form.password });
  } catch (e) {
    form.busy = false;
    toast(e instanceof Error ? e.message : "Login failed", "error");
    return;
  }
  form.busy = false;
  emit("connected");
}
</script>

<template>
  <div class="modal modal-open" @click.self="emit('close')">
    <div ref="modalBox" class="modal-box">
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
          @click="loginTrackerAccount"
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
