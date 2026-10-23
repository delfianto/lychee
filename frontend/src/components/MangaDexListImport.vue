<script setup lang="ts">
import { onUnmounted, ref } from "vue";
import { useRouter } from "vue-router";
import { browseMDLists, importMDList, syncMDLists, type MDListInfo } from "../api/mdlists";
import { onTaskDone } from "../api/events";
import { toast } from "../lib/toast";
const router = useRouter();
const expanded = ref(false);
const reference = ref("");
const kind = ref("list");
const results = ref<MDListInfo[]>([]);
const busy = ref(false);
const taskId = ref<string | null>(null);
async function run(action: () => Promise<unknown>) {
  busy.value = true;
  try {
    await action();
  } catch (e) {
    toast(e instanceof Error ? e.message : "MangaDex request failed", "error");
  } finally {
    busy.value = false;
  }
}
async function importList(value: string) {
  taskId.value = (await importMDList(value)).id;
  toast("List import queued");
}
async function submit() {
  await run(async () => {
    if (kind.value === "user") results.value = await browseMDLists(reference.value);
    else await importList(reference.value);
  });
}
onUnmounted(
  onTaskDone((task) => {
    if (task.id !== taskId.value) return;
    taskId.value = null;
    if (task.status === "failed") toast(task.detail ?? "List import failed", "error");
    else if (typeof task.result?.collectionId === "string")
      void router.push(`/lists/${task.result.collectionId}`);
    else toast("MangaDex lists synced");
  }),
);
</script>
<template>
  <div class="flex flex-col gap-3 rounded-box surface-border bg-base-100 p-3">
    <div class="flex flex-wrap items-center gap-2">
      <span class="font-medium">MangaDex lists</span>
      <button
        class="btn btn-ghost btn-sm"
        :disabled="busy || !!taskId"
        @click="expanded = !expanded"
      >
        Import or browse
      </button>
      <button
        class="btn btn-ghost btn-sm"
        :disabled="busy || !!taskId"
        @click="
          run(async () => {
            taskId = (await syncMDLists()).id;
            toast('List sync queued');
          })
        "
      >
        Sync my lists and followed lists
      </button>
    </div>
    <form v-if="expanded" class="flex flex-wrap items-center gap-2" @submit.prevent="submit">
      <select
        v-model="kind"
        class="select select-bordered select-sm"
        aria-label="MangaDex import type"
      >
        <option value="list">Import a list</option>
        <option value="user">Browse a user's public lists</option>
      </select>
      <input
        v-model="reference"
        class="input input-bordered input-sm min-w-0 grow"
        aria-label="MangaDex URL or UUID"
        placeholder="MangaDex URL or UUID"
      />
      <button class="btn btn-primary btn-sm" :disabled="busy || !!taskId || !reference.trim()">
        {{ kind === "user" ? "Browse" : "Import" }}
      </button>
    </form>
    <ul v-if="expanded && results.length" class="flex flex-col gap-2">
      <li v-for="list in results" :key="list.id" class="flex items-center justify-between gap-3">
        <a
          :href="list.sourceUrl"
          target="_blank"
          rel="noopener noreferrer"
          class="link min-w-0 wrap-anywhere"
          >{{ list.name }} · {{ list.mangaCount }} works</a
        >
        <button
          class="btn btn-sm"
          :disabled="busy || !!taskId"
          @click="run(() => importList(list.id))"
        >
          Import list
        </button>
      </li>
    </ul>
    <p v-if="taskId" class="text-sm text-base-content/60">Working in the background…</p>
  </div>
</template>
