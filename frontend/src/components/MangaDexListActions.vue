<script setup lang="ts">
import { onUnmounted, ref, watch } from "vue";
import { RouterLink } from "vue-router";
import {
  fetchMDListFeed,
  followMDList,
  setListVisibility,
  syncMDLists,
  type MDListChapter,
} from "../api/mdlists";
import { onTaskDone } from "../api/events";
import { toast } from "../lib/toast";
import type { Collection } from "../types";
const props = defineProps<{ collection: Collection }>();
const emit = defineEmits<{ changed: [] }>();
const busy = ref(false);
const feedBusy = ref(false);
const chapters = ref<MDListChapter[]>([]);
const total = ref(0);
const page = ref(0);
const language = ref("");
const visibility = ref<"public" | "private">(props.collection.visibility ?? "private");
const feedError = ref("");
const syncTask = ref<string | null>(null);
watch(
  () => props.collection.visibility,
  (v) => {
    visibility.value = v ?? "private";
  },
);
async function action(work: () => Promise<unknown>, message: string, reload = true) {
  busy.value = true;
  try {
    await work();
    if (reload) emit("changed");
    toast(message);
  } catch (e) {
    visibility.value = props.collection.visibility ?? "private";
    toast(e instanceof Error ? e.message : "MangaDex request failed", "error");
  } finally {
    busy.value = false;
  }
}
async function loadFeed(reset = false) {
  if (feedBusy.value) return;
  feedBusy.value = true;
  feedError.value = "";
  try {
    const next = reset ? 1 : page.value + 1;
    const data = await fetchMDListFeed(props.collection.id, next, language.value || undefined);
    chapters.value = reset ? data.items : [...chapters.value, ...data.items];
    total.value = data.total;
    page.value = next;
  } catch (e) {
    feedError.value = e instanceof Error ? e.message : "Couldn't load updates";
  } finally {
    feedBusy.value = false;
  }
}
onUnmounted(
  onTaskDone((task) => {
    if (task.id !== syncTask.value) return;
    syncTask.value = null;
    if (task.status === "failed") toast(task.detail ?? "List sync failed", "error");
    else {
      emit("changed");
      toast("List synced");
    }
  }),
);
</script>
<template>
  <section class="flex flex-col gap-3 rounded-box surface-border bg-base-100 p-4">
    <div class="flex flex-wrap items-center gap-2">
      <span class="badge badge-outline">MangaDex</span>
      <span class="text-sm">{{
        collection.owned
          ? "Your list"
          : collection.followed
            ? "Followed list · read-only"
            : "Imported list · read-only"
      }}</span>
      <a
        v-if="collection.sourceUrl"
        :href="collection.sourceUrl"
        class="link text-sm"
        target="_blank"
        rel="noopener noreferrer"
        >Open on MangaDex</a
      >
      <button
        class="btn btn-ghost btn-sm"
        :disabled="busy || !!syncTask"
        @click="
          action(
            async () => {
              syncTask = (await syncMDLists(collection.id)).id;
            },
            'List sync queued',
            false,
          )
        "
      >
        Sync list
      </button>
      <button
        v-if="!collection.owned"
        class="btn btn-sm"
        :disabled="busy"
        @click="
          action(
            () => followMDList(collection.id, !collection.followed),
            collection.followed ? 'Unfollowed list' : 'Following list',
          )
        "
      >
        {{ collection.followed ? "Unfollow on MangaDex" : "Follow on MangaDex" }}
      </button>
      <label v-if="collection.owned" class="flex items-center gap-2 text-sm"
        >Visibility
        <select
          v-model="visibility"
          aria-label="List visibility"
          class="select select-bordered select-sm"
          :disabled="busy"
          @change="action(() => setListVisibility(collection.id, visibility), 'Visibility updated')"
        >
          <option value="private">Private</option>
          <option value="public">Public</option>
        </select>
      </label>
      <span v-else class="text-xs text-base-content/60">{{ collection.visibility }}</span>
    </div>
    <p v-if="collection.lastSyncedAt" class="text-xs text-base-content/60">
      Last synced {{ new Date(collection.lastSyncedAt).toLocaleString() }}
    </p>
    <details
      class="group"
      @toggle="
        (e) => {
          if ((e.target as HTMLDetailsElement).open && !page) void loadFeed(true);
        }
      "
    >
      <summary class="cursor-pointer font-medium">Chapter updates</summary>
      <div class="mt-3 flex flex-col gap-3">
        <p class="text-sm text-base-content/60">
          Latest chapters on MangaDex. No download required.
        </p>
        <form class="flex flex-wrap items-center gap-2" @submit.prevent="loadFeed(true)">
          <input
            v-model="language"
            aria-label="List feed language"
            class="input input-bordered input-sm w-32"
            placeholder="Default language"
            pattern="[a-zA-Z-]{2,5}"
          />
          <button class="btn btn-sm" :disabled="feedBusy">Refresh updates</button>
        </form>
        <p v-if="feedError" role="alert" class="text-sm text-error">{{ feedError }}</p>
        <ul class="divide-y divide-base-300">
          <li
            v-for="chapter in chapters"
            :key="chapter.chapterId"
            class="flex flex-wrap items-center justify-between gap-2 py-3"
          >
            <div class="min-w-0">
              <RouterLink
                v-if="chapter.seriesId"
                :to="`/series/${chapter.seriesId}`"
                class="link font-medium wrap-anywhere"
                >{{ chapter.mangaTitle }}</RouterLink
              >
              <a
                v-else
                :href="`https://mangadex.org/title/${chapter.mangaId}`"
                target="_blank"
                rel="noopener noreferrer"
                class="link font-medium wrap-anywhere"
                >{{ chapter.mangaTitle }}</a
              >
              <p class="text-xs text-base-content/60">
                {{ chapter.group }} · {{ chapter.language
                }}<template v-if="chapter.uploadedAt">
                  · {{ new Date(chapter.uploadedAt).toLocaleDateString() }}</template
                >
              </p>
            </div>
            <a
              :href="chapter.sourceUrl"
              class="btn btn-ghost btn-sm"
              target="_blank"
              rel="noopener noreferrer"
              >Chapter {{ chapter.number ?? "Oneshot"
              }}<template v-if="chapter.title"> · {{ chapter.title }}</template></a
            >
          </li>
        </ul>
        <p
          v-if="!feedBusy && page && !chapters.length && !feedError"
          class="text-sm text-base-content/60"
        >
          No chapters in this language.
        </p>
        <button
          v-if="page * 30 < total && page * 30 < 9990"
          class="btn btn-sm self-start"
          :disabled="feedBusy"
          @click="loadFeed()"
        >
          Load more updates
        </button>
        <span
          v-if="feedBusy"
          class="loading loading-spinner loading-sm"
          aria-label="Loading list updates"
        />
      </div>
    </details>
  </section>
</template>
