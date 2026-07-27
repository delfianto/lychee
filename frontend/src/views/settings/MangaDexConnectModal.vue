<script setup lang="ts">
// The MangaDex account connect dialog: a personal API client (client id/secret) plus
// your username/password (OAuth2 password grant). Secrets are encrypted at rest. Emits
// `connected` on success (parent reloads + closes). Supports loading KEY=VAL env files
// so long tokens don't have to be hand-pasted.
import { Eye, EyeOff, FileUp, Link2, X } from "lucide-vue-next";
import { reactive, ref } from "vue";

import { api } from "../../api/client";
import { useFocusTrap } from "../../lib/focusTrap";
import { toast } from "../../lib/toast";

const emit = defineEmits<{ close: []; connected: [] }>();

const form = reactive({ clientId: "", clientSecret: "", username: "", password: "", busy: false });
const showSecret = ref(false);
const showPassword = ref(false);
const fileInput = ref<HTMLInputElement | null>(null);

// No `open` prop — the parent mounts this component only while shown.
const modalBox = ref<HTMLElement | null>(null);
useFocusTrap(modalBox, ref(true));

/** Exact KEY=VAL names → form fields. No aliases. */
const ENV_FIELDS = {
  CLIENT_ID: "clientId",
  CLIENT_SECRET: "clientSecret",
  USERNAME: "username",
  PASSWORD: "password",
} as const;

/** Parse KEY=VAL lines. Comments and blank lines skipped. */
function parseKeyVal(text: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    const eq = line.indexOf("=");
    if (eq <= 0) continue;
    const key = line.slice(0, eq).trim();
    let val = line.slice(eq + 1).trim();
    if (
      (val.startsWith('"') && val.endsWith('"') && val.length >= 2) ||
      (val.startsWith("'") && val.endsWith("'") && val.length >= 2)
    ) {
      val = val.slice(1, -1);
    }
    if (key) out[key] = val;
  }
  return out;
}

function applyEnvFile(text: string): number {
  const pairs = parseKeyVal(text);
  let filled = 0;
  for (const [key, field] of Object.entries(ENV_FIELDS)) {
    const value = pairs[key];
    if (!value) continue;
    form[field] = value;
    filled += 1;
  }
  return filled;
}

function openFilePicker(): void {
  fileInput.value?.click();
}

async function onFileSelected(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = ""; // allow re-picking the same file
  if (!file) return;
  try {
    const text = await file.text();
    const filled = applyEnvFile(text);
    if (filled === 0) {
      toast("No matching keys — need CLIENT_ID, CLIENT_SECRET, USERNAME, PASSWORD", "error");
      return;
    }
    toast(`Loaded ${filled} field${filled === 1 ? "" : "s"} from ${file.name}`);
  } catch {
    toast("Couldn't read that file", "error");
  }
}

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
    <div ref="modalBox" class="modal-box max-w-lg">
      <div class="mb-3 flex items-center justify-between">
        <h3 class="text-lg font-bold">Connect MangaDex</h3>
        <button class="btn btn-circle btn-ghost btn-sm" aria-label="Close" @click="emit('close')">
          <X class="size-4" />
        </button>
      </div>
      <div class="flex flex-col gap-3">
        <p class="text-xs text-base-content/50">
          Create a
          <a href="https://mangadex.org/settings" target="_blank" rel="noopener" class="link">personal API client</a>
          on MangaDex, then sign in to import your follows &amp; reading status. Secrets are encrypted at rest.
        </p>

        <div class="flex flex-wrap items-center justify-between gap-2 rounded-box border border-base-content/10 bg-base-200/30 px-3 py-2">
          <p class="min-w-0 text-xs text-base-content/55">
            Prefill from a file with
            <code class="text-primary/80">CLIENT_ID</code>,
            <code class="text-primary/80">CLIENT_SECRET</code>,
            <code class="text-primary/80">USERNAME</code>,
            <code class="text-primary/80">PASSWORD</code>
            — browser-only.
          </p>
          <button
            type="button"
            class="btn btn-ghost btn-sm gap-1 shrink-0 surface-border"
            :disabled="form.busy"
            @click="openFilePicker"
          >
            <FileUp class="size-4" />Load from file
          </button>
          <input
            ref="fileInput"
            type="file"
            accept=".env,.txt,text/plain,*/*"
            class="hidden"
            @change="onFileSelected"
          />
        </div>

        <div class="flex flex-col gap-1">
          <label class="text-xs text-base-content/60">Client ID</label>
          <input
            v-model="form.clientId"
            class="input input-bordered input-sm w-full font-mono"
            placeholder="Client ID"
            autocomplete="off"
          />
        </div>

        <div class="flex flex-col gap-1">
          <label class="text-xs text-base-content/60">Client secret</label>
          <div class="relative">
            <input
              v-model="form.clientSecret"
              :type="showSecret ? 'text' : 'password'"
              class="input input-bordered input-sm w-full pr-10 font-mono"
              placeholder="Client secret"
              autocomplete="off"
            />
            <button
              type="button"
              class="btn btn-ghost btn-xs btn-square absolute top-1/2 right-1 -translate-y-1/2 text-base-content/50"
              :aria-label="showSecret ? 'Hide client secret' : 'Show client secret'"
              :aria-pressed="showSecret"
              @click="showSecret = !showSecret"
            >
              <EyeOff v-if="showSecret" class="size-4" />
              <Eye v-else class="size-4" />
            </button>
          </div>
        </div>

        <div class="flex flex-col gap-1">
          <label class="text-xs text-base-content/60">Username</label>
          <input
            v-model="form.username"
            class="input input-bordered input-sm w-full"
            placeholder="Username"
            autocomplete="username"
          />
        </div>

        <div class="flex flex-col gap-1">
          <label class="text-xs text-base-content/60">Password</label>
          <div class="relative">
            <input
              v-model="form.password"
              :type="showPassword ? 'text' : 'password'"
              class="input input-bordered input-sm w-full pr-10"
              placeholder="Password"
              autocomplete="current-password"
            />
            <button
              type="button"
              class="btn btn-ghost btn-xs btn-square absolute top-1/2 right-1 -translate-y-1/2 text-base-content/50"
              :aria-label="showPassword ? 'Hide password' : 'Show password'"
              :aria-pressed="showPassword"
              @click="showPassword = !showPassword"
            >
              <EyeOff v-if="showPassword" class="size-4" />
              <Eye v-else class="size-4" />
            </button>
          </div>
        </div>

        <button
          class="btn btn-primary btn-sm mt-1 self-start gap-1"
          :disabled="form.busy || !form.clientId || !form.clientSecret || !form.password"
          @click="connect"
        >
          <Link2 class="size-4" />{{ form.busy ? "Connecting…" : "Connect" }}
        </button>
      </div>
    </div>
  </div>
</template>
