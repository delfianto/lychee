<script setup lang="ts">
// Server-side path picker scoped to the configured storage root.
// Lists directories (and optionally files) via GET /api/fs — used by Add Library
// and Local Import so operators pick a folder instead of typing a path.
import {
  ChevronRight,
  File,
  Folder,
  FolderOpen,
  FolderPlus,
  HardDrive,
  LoaderCircle,
  X,
} from "lucide-vue-next";
import { computed, nextTick, onMounted, onUnmounted, ref } from "vue";

import type { FsEntry, FsListing } from "../api/client";
import { browsePath, makeDirectory } from "../api/settingsQueries";
import { useFocusTrap } from "../lib/focusTrap";

const props = withDefaults(
  defineProps<{
    /** Prefer opening here when it lies under the storage root; otherwise root. */
    initialPath?: string;
    /** When true, a file can be selected (import). Default: directory only. */
    allowFiles?: boolean;
    title?: string;
  }>(),
  {
    initialPath: "",
    allowFiles: false,
    title: "Browse storage",
  },
);

const emit = defineEmits<{ close: []; select: [path: string] }>();

// No `open` prop — the parent mounts this component only while shown.
const modalBox = ref<HTMLElement | null>(null);
useFocusTrap(modalBox, ref(true));

const listing = ref<FsListing | null>(null);
const loading = ref(false);
const error = ref("");
const selectedFile = ref<string | null>(null);

const creating = ref(false);
const newName = ref("");
const createBusy = ref(false);
const createError = ref("");
const nameInput = ref<HTMLInputElement | null>(null);

async function load(path?: string | null, opts: { fallbackRoot?: boolean } = {}): Promise<void> {
  const fallbackRoot = opts.fallbackRoot !== false;
  loading.value = true;
  error.value = "";
  selectedFile.value = null;
  cancelCreate();
  try {
    listing.value = await browsePath(path);
  } catch {
    loading.value = false;
    // Initial path outside storage / missing → open at the storage root once.
    if (path && fallbackRoot) {
      await load(null, { fallbackRoot: false });
      return;
    }
    error.value = "Couldn't read that folder on the server";
    return;
  }
  loading.value = false;
}

const crumbs = computed(() => {
  if (!listing.value) return [] as { label: string; path: string }[];
  const { root, path } = listing.value;
  const rootLabel = root.split("/").filter(Boolean).at(-1) ?? root;
  const out: { label: string; path: string }[] = [{ label: rootLabel, path: root }];
  if (path === root) return out;
  const rel = path.startsWith(`${root}/`) ? path.slice(root.length + 1) : "";
  let acc = root;
  for (const part of rel.split("/").filter(Boolean)) {
    acc = `${acc}/${part}`;
    out.push({ label: part, path: acc });
  }
  return out;
});

const canSelect = computed(() => {
  if (selectedFile.value) return true;
  return Boolean(listing.value?.path);
});

function openDir(path: string): void {
  void load(path, { fallbackRoot: false });
}

function onEntryActivate(entry: FsEntry): void {
  if (entry.kind === "dir") {
    openDir(entry.path);
    return;
  }
  if (props.allowFiles) selectedFile.value = entry.path;
}

function confirm(): void {
  if (!canSelect.value) return;
  if (selectedFile.value) {
    emit("select", selectedFile.value);
    return;
  }
  if (listing.value) emit("select", listing.value.path);
}

async function startCreate(): Promise<void> {
  if (!listing.value || loading.value) return;
  creating.value = true;
  newName.value = "";
  createError.value = "";
  await nextTick();
  nameInput.value?.focus();
}

function cancelCreate(): void {
  creating.value = false;
  newName.value = "";
  createError.value = "";
  createBusy.value = false;
}

async function submitCreate(): Promise<void> {
  if (!listing.value || createBusy.value) return;
  const name = newName.value.trim();
  if (!name) {
    createError.value = "Enter a folder name";
    return;
  }
  createBusy.value = true;
  createError.value = "";
  const parent = listing.value.path;
  try {
    listing.value = await makeDirectory(parent, name);
  } catch (e) {
    createBusy.value = false;
    createError.value = e instanceof Error ? e.message : "Couldn't create the folder";
    return;
  }
  createBusy.value = false;
  cancelCreate();
}

function onKey(e: KeyboardEvent): void {
  if (e.key === "Escape") {
    if (creating.value) {
      e.stopPropagation();
      cancelCreate();
      return;
    }
    emit("close");
  }
}

onMounted(() => {
  document.body.classList.add("overflow-hidden");
  window.addEventListener("keydown", onKey);
  void load(props.initialPath.trim() || null);
});
onUnmounted(() => {
  document.body.classList.remove("overflow-hidden");
  window.removeEventListener("keydown", onKey);
});
</script>

<template>
  <!-- Teleport + z above daisyUI .modal (z-index: 999) so this stacks over Add library. -->
  <Teleport to="body">
    <div
      class="modal modal-open !z-[1100]"
      role="dialog"
      aria-modal="true"
      @click.self="emit('close')"
    >
      <div ref="modalBox" class="modal-box flex max-h-[min(36rem,90vh)] max-w-xl flex-col gap-0 p-0">
        <div class="flex items-start justify-between gap-3 border-b border-base-content/10 px-5 py-4">
          <div class="min-w-0">
            <h3 class="text-lg font-bold">{{ title }}</h3>
            <p class="mt-0.5 text-xs text-base-content/50">
              Folders under the server storage root — pick one instead of typing the path.
            </p>
          </div>
          <button
            type="button"
            class="btn btn-circle btn-ghost btn-sm shrink-0"
            aria-label="Close"
            @click="emit('close')"
          >
            <X class="size-4" />
          </button>
        </div>

        <!-- Breadcrumb + New folder -->
        <div
          v-if="listing"
          class="flex items-center gap-2 border-b border-base-content/10 px-3 py-2"
        >
          <div class="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto text-xs">
            <HardDrive class="size-3.5 shrink-0 text-base-content/40" />
            <template v-for="(crumb, i) in crumbs" :key="crumb.path">
              <ChevronRight v-if="i > 0" class="size-3 shrink-0 text-base-content/30" />
              <button
                type="button"
                class="shrink-0 rounded px-1 py-0.5 hover:bg-base-content/10"
                :class="i === crumbs.length - 1 ? 'font-medium text-base-content' : 'text-base-content/60'"
                :disabled="i === crumbs.length - 1"
                @click="openDir(crumb.path)"
              >
                {{ crumb.label }}
              </button>
            </template>
          </div>
          <button
            type="button"
            class="btn btn-ghost btn-xs gap-1 shrink-0"
            :disabled="loading || creating"
            title="Create a new folder here"
            @click="startCreate"
          >
            <FolderPlus class="size-3.5" />New folder
          </button>
        </div>

        <!-- Listing -->
        <div class="min-h-0 flex-1 overflow-y-auto px-2 py-2">
          <div
            v-if="creating"
            class="mb-2 flex flex-col gap-1.5 rounded-lg border border-base-content/15 bg-base-200/40 p-2"
          >
            <div class="flex items-center gap-2">
              <Folder class="size-4 shrink-0 text-warning" />
              <input
                ref="nameInput"
                v-model="newName"
                type="text"
                class="input input-bordered input-sm min-w-0 flex-1 font-mono"
                placeholder="Folder name"
                :disabled="createBusy"
                @keyup.enter="submitCreate"
                @keyup.escape.stop="cancelCreate"
              />
              <button
                type="button"
                class="btn btn-primary btn-sm"
                :disabled="createBusy || !newName.trim()"
                @click="submitCreate"
              >
                <span v-if="createBusy" class="loading loading-spinner loading-xs" />
                Create
              </button>
              <button type="button" class="btn btn-ghost btn-sm" :disabled="createBusy" @click="cancelCreate">
                Cancel
              </button>
            </div>
            <p v-if="createError" class="px-1 text-xs text-error">{{ createError }}</p>
          </div>

          <div v-if="loading" class="flex items-center justify-center gap-2 py-16 text-sm text-base-content/50">
            <LoaderCircle class="size-4 animate-spin" />Loading…
          </div>
          <div v-else-if="error" class="px-3 py-12 text-center text-sm text-error">{{ error }}</div>
          <div
            v-else-if="listing && listing.entries.length === 0 && !creating"
            class="px-3 py-12 text-center text-sm text-base-content/40"
          >
            Empty folder
          </div>
          <ul v-else-if="listing && listing.entries.length > 0" class="menu menu-sm w-full gap-0.5 p-0">
            <li v-if="listing.parent">
              <button type="button" class="rounded-lg font-mono" @click="openDir(listing.parent)">
                <FolderOpen class="size-4 text-base-content/50" />
                <span class="text-base-content/70">..</span>
              </button>
            </li>
            <li v-for="entry in listing.entries" :key="entry.path">
              <button
                type="button"
                class="rounded-lg"
                :class="{
                  'opacity-50': entry.kind === 'file' && !allowFiles,
                  active: selectedFile === entry.path,
                }"
                :disabled="entry.kind === 'file' && !allowFiles"
                @click="onEntryActivate(entry)"
                @dblclick="entry.kind === 'dir' ? openDir(entry.path) : undefined"
              >
                <Folder v-if="entry.kind === 'dir'" class="size-4 text-warning" />
                <File v-else class="size-4 text-base-content/40" />
                <span class="truncate font-mono text-xs">{{ entry.name }}</span>
              </button>
            </li>
          </ul>
        </div>

        <!-- Footer -->
        <div class="flex flex-col gap-2 border-t border-base-content/10 px-5 py-3">
          <div class="truncate font-mono text-[11px] text-base-content/45" :title="listing?.path">
            {{ selectedFile ?? listing?.path ?? "—" }}
          </div>
          <div class="flex justify-end gap-2">
            <button type="button" class="btn btn-ghost btn-sm" @click="emit('close')">Cancel</button>
            <button
              type="button"
              class="btn btn-primary btn-sm gap-1"
              :disabled="!canSelect || loading"
              @click="confirm"
            >
              <FolderOpen class="size-4" />
              {{ selectedFile ? "Use this file" : "Use this folder" }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>
