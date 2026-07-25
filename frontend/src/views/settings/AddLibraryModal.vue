<script setup lang="ts">
// The "add library" dialog: register a folder on the server as a library root, with
// a name and kind. Replaces the old two-step window.prompt() flow. Emits `added` on
// success (parent reloads + closes).
import { FolderPlus, X } from "lucide-vue-next";
import { reactive } from "vue";

import { api } from "../../api/client";
import { toast } from "../../lib/toast";

const emit = defineEmits<{ close: []; added: [] }>();

const form = reactive({ name: "", path: "", kind: "manga", busy: false });

async function add(): Promise<void> {
  form.busy = true;
  const { error } = await api.POST("/api/libraries", {
    body: { name: form.name.trim(), path: form.path.trim(), kind: form.kind },
  });
  form.busy = false;
  if (error) {
    toast("Couldn't add library — check the path exists on the server", "error");
    return;
  }
  emit("added");
}
</script>

<template>
  <div class="modal modal-open" @click.self="emit('close')">
    <div class="modal-box">
      <div class="mb-3 flex items-center justify-between">
        <h3 class="text-lg font-bold">Add library</h3>
        <button class="btn btn-circle btn-ghost btn-sm" aria-label="Close" @click="emit('close')">
          <X class="size-4" />
        </button>
      </div>
      <div class="flex flex-col gap-2">
        <p class="mb-1 text-xs text-base-content/50">
          Register a folder on the server as a library root — lychee scans it for series &amp; chapters.
        </p>
        <label class="text-xs text-base-content/60">Name</label>
        <input v-model="form.name" class="input input-bordered input-sm" placeholder="e.g. Manga" />
        <label class="mt-1 text-xs text-base-content/60">Path (a folder on the server)</label>
        <input v-model="form.path" class="input input-bordered input-sm font-mono" placeholder="/data/manga" />
        <label class="mt-1 text-xs text-base-content/60">Kind</label>
        <select v-model="form.kind" class="select select-bordered select-sm">
          <option value="manga">Manga</option>
          <option value="comic">Comic</option>
          <option value="gallery">Gallery</option>
        </select>
        <button
          class="btn btn-primary btn-sm mt-2 self-start gap-1"
          :disabled="form.busy || !form.name.trim() || !form.path.trim()"
          @click="add"
        >
          <FolderPlus class="size-4" />{{ form.busy ? "Adding…" : "Add library" }}
        </button>
      </div>
    </div>
  </div>
</template>
