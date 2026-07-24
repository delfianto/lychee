// Read queries over the typed client, mapping API responses to the UI types in
// ../types. The API returns wider unions (plain strings) and ISO timestamps; the
// boundary cast + relativeTime bridge them so components stay strictly typed.

import { computed, ref } from "vue";

import type { BrowseFilters, RecentUpdate, Series } from "../types";
import { type Series as ApiSeries, api, type RecentUpdate as ApiUpdate } from "./client";
import { relativeTime } from "./format";
import type { paths } from "./schema";

function toSeries(s: ApiSeries): Series {
  return s as unknown as Series;
}

function toUpdate(u: ApiUpdate): RecentUpdate {
  return {
    series: toSeries(u.series),
    volume: u.volume,
    chapter: u.chapter,
    updatedAt: relativeTime(u.updatedAt),
  };
}

export interface DashboardData {
  stats: { series: number; unreadChapters: number; reading: number };
  continueReading: Series[];
  recentUpdates: RecentUpdate[];
  recentlyAdded: Series[];
}

export async function fetchDashboard(): Promise<DashboardData> {
  const { data, error } = await api.GET("/api/dashboard");
  if (error || !data) throw new Error("Failed to load dashboard");
  return {
    stats: data.stats,
    continueReading: data.continueReading.map(toSeries),
    recentUpdates: data.recentUpdates.map(toUpdate),
    recentlyAdded: data.recentlyAdded.map(toSeries),
  };
}

export interface LibrarySummary {
  key: string;
  title: string;
  sizeGb: number;
}

export async function fetchLibrarySummaries(): Promise<LibrarySummary[]> {
  const { data, error } = await api.GET("/api/libraries/summary");
  if (error || !data) throw new Error("Failed to load library summary");
  return data;
}

// --- series grids (cursor pagination) ------------------------------------------

export type SeriesQuery = NonNullable<paths["/api/series"]["get"]["parameters"]["query"]>;

/** Cursor-paginated series list: accumulate pages, fetch more on demand. */
export function useSeriesList() {
  const items = ref<Series[]>([]);
  const loading = ref(false);
  const done = ref(false);
  const cursor = ref<string | null>(null);
  let params: SeriesQuery = {};

  async function fetchPage(reset: boolean): Promise<void> {
    if (loading.value) return;
    loading.value = true;
    const query: SeriesQuery = { ...params, limit: 24 };
    if (!reset && cursor.value) query.cursor = cursor.value;
    const { data, error } = await api.GET("/api/series", { params: { query } });
    if (!error && data) {
      const mapped = data.items.map(toSeries);
      items.value = reset ? mapped : [...items.value, ...mapped];
      cursor.value = data.nextCursor ?? null;
      done.value = !data.nextCursor;
    }
    loading.value = false;
  }

  async function reload(next: SeriesQuery): Promise<void> {
    params = next;
    cursor.value = null;
    done.value = false;
    items.value = [];
    await fetchPage(true);
  }

  function loadMore(): void {
    if (!done.value && !loading.value) void fetchPage(false);
  }

  return { items, loading, hasMore: computed(() => !done.value), reload, loadMore };
}

const SORT_MAP: Record<string, string> = {
  "Recently Added": "recentlyAdded",
  "Recently Updated": "recentlyUpdated",
  Title: "title",
  Rating: "rating",
  Unread: "unread",
};

/** Map a library route + filter UI state to /api/series query params. */
export function buildLibraryQuery(
  libraryKey: string,
  opts: { activeTab: string; filters: BrowseFilters; sort: string },
): SeriesQuery {
  const q: SeriesQuery = {};
  if (libraryKey === "comics") q.kind = "comic";
  else if (libraryKey === "gallery") q.kind = "gallery";
  else if (libraryKey === "favorites") q.favorite = true;
  else if (libraryKey === "reading") q.shelf = "reading";
  else q.kind = "manga";

  if (libraryKey !== "reading" && opts.activeTab !== "all") q.shelf = opts.activeTab;

  const f = opts.filters;
  if (f.query.trim()) q.q = f.query.trim();
  const tags = Object.entries(f.tags).map(([id, state]) => (state === "exclude" ? `-${id}` : id));
  if (tags.length) {
    q.tags = tags.join(",");
    q.tagMode = f.tagMode;
  }
  if (f.ratings.size) q.ratings = [...f.ratings].join(",");
  if (f.demographics.size) q.demographics = [...f.demographics].join(",");
  if (f.statuses.size) q.pubStatus = [...f.statuses].join(",");
  if (f.readStates.size === 1) q.readState = [...f.readStates][0];
  q.sort = SORT_MAP[opts.sort] ?? "recentlyAdded";
  return q;
}
