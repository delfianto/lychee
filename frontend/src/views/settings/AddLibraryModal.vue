<script setup lang="ts">
// The "add library" dialog: register a folder on the server as a library root, with
// a name and kind. Path can be typed or picked via the shared storage browser.
// Emits `added` on success (parent reloads + closes).
import { FolderPlus, X } from "lucide-vue-next";
import { reactive, ref } from "vue";

import { api } from "../../api/client";
import ServerPathField from "../../components/ServerPathField.vue";
import { useFocusTrap } from "../../lib/focusTrap";
import { toast } from "../../lib/toast";

const emit = defineEmits<{ close: []; added: [] }>();

const form = reactive({ name: "", path: "", kind: "manga", busy: false });

// No `open` prop — the parent mounts this component only while shown.
const modalBox = ref<HTMLElement | null>(null);
useFocusTrap(modalBox, ref(true));

function onPathPicked(path: string): void {
  // Suggest a name from the folder when the name field is still empty.
  if (!form.name.trim()) {
    const base = path.split("/").filter(Boolean).at(-1);
    if (base) form.name = base;
  }
}

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
    <div ref="modalBox" class="modal-box">
      <div class="mb-3 flex items-center justify-between">
        <h3 class="text-lg font-bold">Add library</h3>
        <button class="btn btn-circle btn-ghost btn-sm" aria-label="Close" @click="emit('close')">
          <X class="size-4" />
        </button>
      </div>
      <div class="flex flex-col gap-3">
        <p class="text-xs text-base-content/50">
          Register a folder on the server as a library root — lychee scans it for series &amp; chapters.
        </p>
        <!-- Shared row layout: flex-1 field + fixed-width trailing control, same gap-2. -->
        <div class="flex items-end gap-2">
          <div class="flex min-w-0 flex-1 flex-col gap-1">
            <label class="text-xs text-base-content/60">Name</label>
            <input v-model="form.name" class="input input-bordered input-sm w-full" placeholder="e.g. Manga" />
          </div>
          <div class="flex w-28 shrink-0 flex-col gap-1">
            <label class="text-xs text-base-content/60">Kind</label>
            <select v-model="form.kind" class="select select-bordered select-sm w-full">
              <option value="manga">Manga</option>
              <option value="comic">Comic</option>
              <option value="gallery">Gallery</option>
            </select>
          </div>
        </div>
        <ServerPathField
          v-model="form.path"
          label="Path (a folder on the server)"
          placeholder="/data/manga"
          browser-title="Choose library folder"
          @pick="onPathPicked"
        />
        <button
          class="btn btn-primary btn-sm mt-1 self-start gap-1"
          :disabled="form.busy || !form.name.trim() || !form.path.trim()"
          @click="add"
        >
          <FolderPlus class="size-4" />{{ form.busy ? "Adding…" : "Add library" }}
        </button>
      </div>
    </div>
  </div>
</template>
