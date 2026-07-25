<script setup lang="ts">
// The MangaDex account connect dialog: a personal API client (client id/secret) plus
// your username/password (OAuth2 password grant). Secrets are encrypted at rest. Emits
// `connected` on success (parent reloads + closes).
import { Link2, X } from "lucide-vue-next";
import { reactive } from "vue";

import { api } from "../../api/client";
import { toast } from "../../lib/toast";

const emit = defineEmits<{ close: []; connected: [] }>();

const form = reactive({ clientId: "", clientSecret: "", username: "", password: "", busy: false });

async function connect(): Promise<void> {
  form.busy = true;
  const { error } = await api.POST("/api/providers/{provider_id}/connect", {
    params: { path: { provider_id: "mangadex" } },
    body: {
      clientId: form.clientId,
      clientSecret: form.clientSecret,
      username: form.username,
      password: form.password,
    },
  });
  form.busy = false;
  if (error) {
    toast("Connect failed — check credentials & LYCHEE_SECRET_KEY", "error");
    return;
  }
  emit("connected");
}
</script>

<template>
  <div class="modal modal-open" @click.self="emit('close')">
    <div class="modal-box">
      <div class="mb-3 flex items-center justify-between">
        <h3 class="text-lg font-bold">Connect MangaDex</h3>
        <button class="btn btn-circle btn-ghost btn-sm" aria-label="Close" @click="emit('close')">
          <X class="size-4" />
        </button>
      </div>
      <div class="flex flex-col gap-2">
        <p class="mb-1 text-xs text-base-content/50">
          Create a
          <a href="https://mangadex.org/settings" target="_blank" rel="noopener" class="link">personal API client</a>
          on MangaDex, then sign in to import your follows &amp; reading status. Secrets are encrypted at rest.
        </p>
        <input v-model="form.clientId" class="input input-bordered input-sm" placeholder="Client ID" />
        <input v-model="form.clientSecret" type="password" class="input input-bordered input-sm" placeholder="Client secret" />
        <input v-model="form.username" class="input input-bordered input-sm" placeholder="Username" />
        <input v-model="form.password" type="password" class="input input-bordered input-sm" placeholder="Password" />
        <button
          class="btn btn-primary btn-sm self-start gap-1"
          :disabled="form.busy || !form.clientId || !form.clientSecret || !form.password"
          @click="connect"
        >
          <Link2 class="size-4" />{{ form.busy ? "Connecting…" : "Connect" }}
        </button>
      </div>
    </div>
  </div>
</template>
