<script setup lang="ts">
import {
  ArrowDown,
  ArrowUp,
  BookMarked,
  BookOpen,
  ChevronRight,
  HardDrive,
  Library,
  Settings,
  Shuffle,
  SlidersHorizontal,
  X,
} from "@lucide/vue";
import {
  computed,
  onActivated,
  onDeactivated,
  onMounted,
  onUnmounted,
  reactive,
  ref,
  watch,
} from "vue";
import { RouterLink, type RouteLocationRaw } from "vue-router";
import {
  buildLibraryQuery,
  fetchDashboard,
  fetchHomeSection,
  fetchLibrarySummaries,
  fetchSeriesPage,
  type HomePage,
  type LibrarySummary,
} from "../api/queries";
import { onTaskDone } from "../api/events";
import ErrorState from "../components/ErrorState.vue";
import RecentUpdates from "../components/RecentUpdates.vue";
import SeriesRail from "../components/SeriesRail.vue";
import { useRecentlyAddedKinds } from "../lib/density";
import { toast } from "../lib/toast";
import { useCollections } from "../stores/collections";
import { HOME_SECTIONS, useHome, type HomePin, type HomeSection } from "../stores/home";
import { presetFilters, usePresets } from "../stores/presets";

defineOptions({ name: "LibraryHome" });
const home = useHome();
const collections = useCollections();
const presets = usePresets();
const { recentlyAddedKinds } = useRecentlyAddedKinds();
const loading = ref(true),
  failed = ref(false),
  refreshing = ref(false),
  customize = ref(false);
const stats = ref({ series: 0, unreadChapters: 0, reading: 0 });
const storageLibs = ref<LibrarySummary[]>([]);
interface ShelfState extends HomePage {
  loading: boolean;
  error: string;
}
const shelves = reactive<Record<string, ShelfState>>({});
function state(id: string): ShelfState {
  shelves[id] ??= { items: [], updates: [], nextCursor: null, loading: false, error: "" };
  return shelves[id]!;
}
let generation = 0,
  initialized = false;
let active = true,
  dirty = false;
let refreshTimer: ReturnType<typeof setTimeout> | undefined;
function scheduleRefresh(): void {
  dirty = true;
  if (refreshTimer) clearTimeout(refreshTimer);
  if (!active) return;
  refreshTimer = setTimeout(() => {
    if (active && !refreshing.value) void load(true);
  }, 250);
}
const PAGE_SIZE = 24;
const parameters = () => ({
  limit: PAGE_SIZE,
  discoveryKind: home.preferences.discoveryKind,
  seed: home.seed,
  following: home.preferences.following,
  recentlyAddedKinds: recentlyAddedKinds.value.join(",") || "none",
});
const isEmpty = computed(
  () => !loading.value && !failed.value && !stats.value.series && !storageLibs.value.length,
);

function merge(first: HomePage, next: HomePage): HomePage {
  return {
    items: [...new Map([...first.items, ...next.items].map((s) => [s.id, s])).values()],
    updates: [...first.updates, ...next.updates],
    nextCursor: next.nextCursor,
  };
}
async function restoreDepth(
  first: HomePage,
  minimum: number,
  next: (cursor: string) => Promise<HomePage>,
): Promise<HomePage> {
  let result = first;
  const seen = new Set<string>();
  while (
    result.nextCursor &&
    result.items.length + result.updates.length < minimum &&
    !seen.has(result.nextCursor)
  ) {
    seen.add(result.nextCursor);
    result = merge(result, await next(result.nextCursor));
  }
  return result;
}
async function load(preserveDepth = false): Promise<void> {
  dirty = false;
  const token = ++generation,
    params = parameters();
  loading.value = !initialized;
  refreshing.value = true;
  failed.value = false;
  try {
    const [dashboard, summaries] = await Promise.all([
      fetchDashboard(recentlyAddedKinds.value, params),
      fetchLibrarySummaries(),
    ]);
    const pages = await Promise.all(
      HOME_SECTIONS.map(async ({ id }) => {
        const first: HomePage = {
          items: id === "recentUpdates" ? [] : dashboard[id],
          updates: id === "recentUpdates" ? dashboard.recentUpdates : [],
          nextCursor: dashboard.cursors[id] ?? null,
        };
        const old = state(id);
        const minimum = preserveDepth ? old.items.length + old.updates.length : 0;
        return [
          id,
          await restoreDepth(first, minimum, (cursor) =>
            fetchHomeSection(id, { ...params, cursor }),
          ),
        ] as const;
      }),
    );
    if (token !== generation) return;
    stats.value = dashboard.stats;
    storageLibs.value = summaries.filter((lib) => lib.sizeGb > 0);
    for (const [id, page] of pages) Object.assign(state(id), page, { loading: false, error: "" });
    initialized = true;
    void loadPins(preserveDepth);
  } catch {
    if (token !== generation) return;
    if (initialized)
      toast("Couldn't refresh Home. Your current shelves are still available.", "error");
    else failed.value = true;
  } finally {
    if (token === generation) {
      loading.value = false;
      refreshing.value = false;
      for (const { id } of HOME_SECTIONS) state(id).loading = false;
      if (dirty) scheduleRefresh();
    }
  }
}

function pinTitle(pin: HomePin): string {
  return pin.type === "list"
    ? (collections.getList(pin.collectionId)?.name ?? "Pinned list")
    : pin.name;
}
async function pinPage(pin: HomePin, cursor?: string): Promise<HomePage> {
  if (pin.type === "list")
    return fetchSeriesPage({
      collectionId: pin.collectionId,
      sort: "title",
      limit: PAGE_SIZE,
      cursor,
    });
  const preset = presets.presets.find((p) => p.name === pin.name);
  if (!preset)
    throw new Error("This saved filter was removed. Unpin it or save it again in the library.");
  return fetchSeriesPage({
    ...buildLibraryQuery(pin.libraryKey, {
      activeTab: "all",
      filters: presetFilters(preset),
      sort: "Recently Added",
    }),
    limit: PAGE_SIZE,
    cursor,
  });
}
const pinEpochs = new Map<string, number>();
const pinKeys = new Map<string, string>();
function pinKey(pin: HomePin): string {
  return JSON.stringify([
    pin,
    pin.type === "filter" ? presets.presets.find((p) => p.name === pin.name) : null,
  ]);
}
async function loadPin(pin: HomePin, preserveDepth: boolean): Promise<void> {
  const current = state(pin.id),
    token = (pinEpochs.get(pin.id) ?? 0) + 1;
  pinEpochs.set(pin.id, token);
  pinKeys.set(pin.id, pinKey(pin));
  current.loading = true;
  current.error = "";
  try {
    const first = await pinPage(pin);
    const result = await restoreDepth(first, preserveDepth ? current.items.length : 0, (cursor) =>
      pinPage(pin, cursor),
    );
    if (pinEpochs.get(pin.id) !== token || !home.preferences.pins.some((p) => p.id === pin.id))
      return;
    Object.assign(current, result);
  } catch (error) {
    if (pinEpochs.get(pin.id) === token)
      current.error = error instanceof Error ? error.message : "Couldn't load this shelf";
  } finally {
    if (pinEpochs.get(pin.id) === token) current.loading = false;
  }
}
async function loadPins(preserveDepth = false, onlyChanged = false): Promise<void> {
  for (const id of pinKeys.keys()) {
    if (!home.visible(id) || !home.preferences.pins.some((pin) => pin.id === id))
      pinKeys.delete(id);
  }
  await Promise.all(
    home.preferences.pins
      .filter(
        (pin) => home.visible(pin.id) && (!onlyChanged || pinKeys.get(pin.id) !== pinKey(pin)),
      )
      .map((pin) => loadPin(pin, preserveDepth)),
  );
}
async function more(id: string): Promise<void> {
  const current = state(id),
    token = generation,
    cursor = current.nextCursor;
  if (current.loading || !cursor) return;
  const pin = home.preferences.pins.find((p) => p.id === id);
  const pinToken = pinEpochs.get(id);
  current.loading = true;
  current.error = "";
  try {
    const next = pin
      ? await pinPage(pin, cursor)
      : await fetchHomeSection(id as HomeSection, { ...parameters(), cursor });
    if (token === generation && pinToken === pinEpochs.get(id))
      Object.assign(current, merge(current, next));
  } catch (error) {
    if (token === generation && pinToken === pinEpochs.get(id))
      current.error = error instanceof Error ? error.message : "Couldn't load more";
  } finally {
    if (token === generation && pinToken === pinEpochs.get(id)) current.loading = false;
  }
}

const sections = computed(() =>
  home.preferences.order
    .map((id) => {
      const builtin = HOME_SECTIONS.find((s) => s.id === id),
        pin = home.preferences.pins.find((p) => p.id === id);
      if (!builtin && !pin) return null;
      let href: RouteLocationRaw | undefined,
        linkLabel = "";
      if (id === "readingList") {
        href = "/reading";
        linkLabel = "See your full reading list";
      }
      if (id === "recentUpdates") {
        href = "/updates";
        linkLabel = "See all updates";
      }
      if (id === "recentlyAdded") {
        href = "/added";
        linkLabel = "See all recently added";
      }
      if (pin)
        href =
          pin.type === "list"
            ? `/lists/${pin.collectionId}`
            : { path: `/${pin.libraryKey}`, query: { preset: pin.name } };
      const title = builtin?.title ?? pinTitle(pin!);
      return { id, title, href, linkLabel: linkLabel || `See all ${title}`, pin, state: state(id) };
    })
    .filter((s) => s !== null),
);
const visibleSections = computed(() =>
  sections.value.filter(
    (s) =>
      home.visible(s.id) &&
      (s.state.items.length ||
        s.state.updates.length ||
        s.state.error ||
        (s.pin && s.state.loading)),
  ),
);

onMounted(() => void load());
onActivated(() => {
  active = true;
  if (home.refreshDay()) return;
  if (initialized && !refreshing.value) void load(true);
});
onDeactivated(() => {
  active = false;
  if (refreshTimer) clearTimeout(refreshTimer);
});
watch(
  [
    recentlyAddedKinds,
    () => home.preferences.discoveryKind,
    () => home.preferences.following,
    () => home.seed,
  ],
  () => {
    if (active) void load(true);
    else dirty = true;
  },
);
watch(
  [() => home.preferences.pins, () => home.preferences.hidden, () => presets.presets],
  () => {
    if (initialized && active) void loadPins(false, true);
  },
  { deep: true },
);
const stopTasks = onTaskDone((task) => {
  if (
    task.status === "done" &&
    ["import", "scan", "metadata", "mdlist", "download"].includes(task.kind)
  )
    scheduleRefresh();
});
onUnmounted(() => {
  generation += 1;
  if (refreshTimer) clearTimeout(refreshTimer);
  pinEpochs.clear();
  pinKeys.clear();
  stopTasks();
});
</script>

<template>
  <div
    class="flex flex-col gap-6 p-4 sm:p-6"
    :data-browse-loading="loading || refreshing || undefined"
  >
    <div class="flex flex-wrap items-center justify-between gap-3">
      <h1 class="text-2xl font-bold">Home</h1>
      <button
        class="btn btn-ghost btn-sm gap-2 surface-border"
        :aria-expanded="customize"
        aria-controls="home-customization"
        @click="customize = !customize"
      >
        <SlidersHorizontal class="size-4" />Customize Home
      </button>
    </div>
    <div
      v-if="customize"
      id="home-customization"
      class="flex flex-col gap-4 rounded-box bg-base-100 p-4 surface-border"
    >
      <div class="flex flex-wrap items-center gap-4">
        <label class="flex items-center gap-2 text-sm"
          >Discover<select
            v-model="home.preferences.discoveryKind"
            class="select select-sm w-32"
            aria-label="Discovery library"
          >
            <option value="manga">Manga</option>
            <option value="comic">Comics</option>
          </select></label
        >
        <label class="flex items-center gap-2 text-sm"
          ><input
            v-model="home.preferences.following"
            type="checkbox"
            class="checkbox checkbox-sm"
          />Updates from reading list and favorites only</label
        >
        <button class="btn btn-ghost btn-sm ml-auto" @click="home.reset()">Reset Home</button>
      </div>
      <div class="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
        <div
          v-for="(shelf, index) in sections"
          :key="shelf.id"
          class="flex items-center gap-2 rounded-field bg-base-200 p-2"
        >
          <label class="flex min-w-0 grow items-center gap-2 text-sm"
            ><input
              class="checkbox checkbox-sm"
              type="checkbox"
              :checked="home.visible(shelf.id)"
              :aria-label="`Show ${shelf.title}`"
              @change="home.toggle(shelf.id)"
            /><span class="truncate">{{ shelf.title }}</span></label
          >
          <button
            class="btn btn-square btn-ghost btn-xs"
            :disabled="index === 0"
            :aria-label="`Move ${shelf.title} up`"
            @click="home.move(shelf.id, -1)"
          >
            <ArrowUp class="size-3.5" />
          </button>
          <button
            class="btn btn-square btn-ghost btn-xs"
            :disabled="index === sections.length - 1"
            :aria-label="`Move ${shelf.title} down`"
            @click="home.move(shelf.id, 1)"
          >
            <ArrowDown class="size-3.5" />
          </button>
          <button
            v-if="shelf.pin"
            class="btn btn-square btn-ghost btn-xs"
            :aria-label="`Unpin ${shelf.title} ${shelf.pin.type}`"
            @click="home.unpin(shelf.id)"
          >
            <X class="size-3.5" />
          </button>
        </div>
      </div>
      <p class="text-xs text-base-content/60">
        Use “Show on Home” on a list, or pin a saved filter in Manga or Comics, to add your own
        shelf. These preferences are saved in this browser.
      </p>
    </div>
    <div v-if="loading" class="flex flex-col gap-5" aria-label="Loading Home">
      <div class="h-10 animate-pulse rounded-box bg-base-300" />
      <div class="grid grid-cols-2 gap-4 sm:grid-cols-4 lg:grid-cols-6">
        <div v-for="i in 6" :key="i" class="cover animate-pulse rounded-box bg-base-300" />
      </div>
    </div>
    <ErrorState v-else-if="failed" message="Couldn't load your dashboard." @retry="load()" />
    <div
      v-else-if="isEmpty"
      class="flex flex-col items-center gap-4 rounded-box bg-base-100 px-6 py-16 text-center surface-border"
    >
      <Library class="size-12 text-primary/70" />
      <h2 class="text-2xl font-bold">Your library is empty</h2>
      <p class="max-w-md text-sm text-base-content/70">
        Add a local library folder, import archives, or connect MangaDex to sync your follows — then
        your shelves will fill in here.
      </p>
      <RouterLink to="/settings" class="btn btn-primary gap-1.5"
        ><Settings class="size-4" />Open settings</RouterLink
      >
    </div>
    <template v-else>
      <div
        class="flex flex-wrap items-center gap-x-5 gap-y-2 rounded-box bg-base-100 px-4 py-3 text-sm surface-border"
      >
        <RouterLink to="/manga" class="link link-hover inline-flex items-center gap-2"
          ><Library class="size-4 text-primary" /><strong>{{ stats.series }}</strong>
          series</RouterLink
        >
        <RouterLink to="/unread" class="link link-hover inline-flex items-center gap-2"
          ><BookOpen class="size-4 text-primary" /><strong>{{ stats.unreadChapters }}</strong>
          unread chapters</RouterLink
        >
        <RouterLink to="/reading" class="link link-hover inline-flex items-center gap-2"
          ><BookMarked class="size-4 text-primary" /><strong>{{ stats.reading }}</strong>
          reading</RouterLink
        >
        <RouterLink
          v-for="lib in storageLibs"
          :key="lib.key"
          :to="`/${lib.key}`"
          class="link link-hover inline-flex items-center gap-2 text-base-content/60"
          ><HardDrive class="size-4" />{{ lib.title }} · {{ lib.sizeGb }} GB</RouterLink
        >
      </div>
      <section
        v-for="shelf in visibleSections"
        :key="shelf.id"
        :aria-label="shelf.title"
        :aria-busy="shelf.state.loading"
        :data-home-section="shelf.id"
        class="flex min-w-0 flex-col gap-3"
      >
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div class="flex items-center gap-2">
            <h2 class="text-lg font-semibold">
              <RouterLink v-if="shelf.href" :to="shelf.href" class="link link-hover">{{
                shelf.title
              }}</RouterLink
              ><template v-else>{{ shelf.title }}</template>
            </h2>
            <span
              v-if="shelf.state.loading && !shelf.state.items.length && !shelf.state.updates.length"
              class="loading loading-spinner loading-xs"
              :aria-label="`Loading ${shelf.title}`"
            />
            <span
              v-else-if="shelf.state.items.length || shelf.state.updates.length"
              class="text-xs text-base-content/50"
              >{{ shelf.state.items.length + shelf.state.updates.length
              }}{{ shelf.state.nextCursor ? "+" : "" }}</span
            >
          </div>
          <div class="flex items-center gap-1">
            <button
              v-if="shelf.id === 'rediscover' || shelf.id === 'quickReads'"
              class="btn btn-ghost btn-sm gap-1.5"
              :disabled="refreshing"
              :aria-label="`Shuffle ${shelf.title}`"
              @click="home.shuffle()"
            >
              <Shuffle class="size-4" />Shuffle
            </button>
            <RouterLink
              v-if="shelf.href"
              :to="shelf.href"
              class="btn btn-circle btn-ghost btn-sm"
              :aria-label="shelf.linkLabel"
              ><ChevronRight class="size-5"
            /></RouterLink>
          </div>
        </div>
        <p v-if="shelf.id === 'rediscover'" class="-mt-2 text-xs text-base-content/60">
          Unread {{ home.preferences.discoveryKind === "comic" ? "comics" : "manga" }} from the
          older end of your library.
        </p>
        <p v-if="shelf.id === 'quickReads'" class="-mt-2 text-xs text-base-content/60">
          Unread oneshots and finished works · up to 200 local pages.
        </p>
        <p
          v-if="shelf.id === 'recentUpdates' && home.preferences.following"
          class="-mt-2 text-xs text-base-content/60"
        >
          From your reading list and favorites.
        </p>
        <div
          v-if="shelf.state.loading && !shelf.state.items.length && !shelf.state.updates.length"
          class="flex gap-4 overflow-hidden"
          role="status"
          :aria-label="`Loading ${shelf.title}`"
        >
          <div v-for="i in 4" :key="i" class="skeleton cover w-36 shrink-0 rounded-box sm:w-44" />
        </div>
        <RecentUpdates
          v-else-if="shelf.id === 'recentUpdates'"
          :updates="shelf.state.updates"
          rail
        />
        <SeriesRail
          v-else
          :series="shelf.state.items"
          :reading="shelf.id === 'continueReading'"
          details
        />
        <p v-if="shelf.state.error" role="alert" class="text-sm text-error">
          {{ shelf.state.error }}
          <button class="link" @click="shelf.pin ? loadPin(shelf.pin, true) : more(shelf.id)">
            Try again
          </button>
        </p>
        <button
          v-if="shelf.state.nextCursor"
          class="btn btn-ghost btn-sm self-center surface-border"
          :aria-label="`Load more ${shelf.title}`"
          :disabled="shelf.state.loading || refreshing"
          @click="more(shelf.id)"
        >
          <span v-if="shelf.state.loading" class="loading loading-spinner loading-xs" />Load more
        </button>
      </section>
      <p v-if="!visibleSections.length" class="py-10 text-center text-base-content/60">
        Nothing to show on these shelves yet. Customize Home or browse your library.
      </p>
    </template>
  </div>
</template>
