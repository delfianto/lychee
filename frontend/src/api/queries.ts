// Read queries over the typed client, mapping API responses to the UI types in
// ../types. The API returns wider unions (plain strings) and ISO timestamps; the
// boundary cast + relativeTime bridge them so components stay strictly typed.

import { computed, ref } from "vue";

import type { BrowseFilters, Chapter, RecentUpdate, Series, VolumeGroup } from "../types";
import {
  type Chapter as ApiChapter,
  type Series as ApiSeries,
  api,
  type RecentUpdate as ApiUpdate,
  type SeriesUpdate,
} from "./client";
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

function toChapter(c: ApiChapter): Chapter {
  return {
    id: c.id ?? null,
    volume: c.volume,
    number: c.number,
    title: c.title ?? undefined,
    group: c.group ?? undefined,
    language: c.language,
    uploadedAt: c.uploadedAt ? relativeTime(c.uploadedAt) : "",
    read: c.read ?? false,
    comments: c.comments ?? 0,
    status: (c.status as Chapter["status"]) ?? "downloaded",
    providerChapterId: c.providerChapterId ?? null,
  };
}

/** Queue one series (or selected remote chapters) for download. */
export async function queueDownload(
  seriesId: string,
  providerChapterIds?: string[],
): Promise<void> {
  const { error, response } = await api.POST("/api/downloads", {
    body: {
      seriesId,
      ...(providerChapterIds?.length ? { providerChapterIds } : {}),
    },
  });
  if (error) {
    const body = error as { error?: { message?: string }; detail?: string };
    const msg =
      body?.error?.message ??
      (typeof body?.detail === "string" ? body.detail : null) ??
      `Download failed (${response.status})`;
    throw new Error(msg);
  }
}

export interface DeleteChapterResult {
  mode: "provider" | "local" | string;
  redownloadable: boolean;
  seriesId: string;
}

/** Remove local chapter files (provider-aware: MD keeps series / re-downloadable). */
export async function deleteChapterLocal(chapterId: string): Promise<DeleteChapterResult> {
  const { data, error, response } = await api.DELETE("/api/chapters/{chapter_id}", {
    params: { path: { chapter_id: chapterId } },
  });
  if (error || !data) {
    const body = error as { error?: { message?: string } } | undefined;
    throw new Error(body?.error?.message ?? `Delete failed (${response.status})`);
  }
  return {
    mode: data.mode,
    redownloadable: data.redownloadable,
    seriesId: data.seriesId,
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

// --- feeds + search ------------------------------------------------------------

export async function fetchUpdates(unread = false, limit = 60): Promise<RecentUpdate[]> {
  const resp = unread
    ? await api.GET("/api/updates/unread", { params: { query: { limit } } })
    : await api.GET("/api/updates", { params: { query: { limit } } });
  if (resp.error || !resp.data) return [];
  return resp.data.items.map(toUpdate);
}

export async function searchSeries(q: string, limit = 30): Promise<Series[]> {
  const { data, error } = await api.GET("/api/search", { params: { query: { q, limit } } });
  if (error || !data) return [];
  return data.map(toSeries);
}

export interface TagGroup {
  group: string;
  tags: { id: string; name: string }[];
}

const _FILTER_GROUPS = ["genre", "theme", "content", "format"];
const _GROUP_LABEL: Record<string, string> = {
  genre: "Genre",
  theme: "Theme",
  content: "Content",
  format: "Format",
};

/** The series-linked tag vocabulary (for the advanced filter panel). */
export async function fetchTagGroups(): Promise<TagGroup[]> {
  const { data } = await api.GET("/api/taxonomy", { params: { query: { pageSize: 500 } } });
  const items = data?.items ?? [];
  return _FILTER_GROUPS.map((g) => ({
    group: _GROUP_LABEL[g],
    tags: items.filter((i) => i.category === g).map((i) => ({ id: i.id, name: i.name })),
  })).filter((g) => g.tags.length > 0);
}

/** A random series id (for the navbar dice), or null if the library is empty. */
export async function randomSeriesId(): Promise<string | null> {
  const { data } = await api.GET("/api/series", { params: { query: { limit: 50 } } });
  const items = data?.items ?? [];
  if (items.length === 0) return null;
  return items[Math.floor(Math.random() * items.length)].id;
}

// --- series grids (cursor pagination) ------------------------------------------

export type SeriesQuery = NonNullable<paths["/api/series"]["get"]["parameters"]["query"]>;

/** Cursor-paginated series list: accumulate pages, fetch more on demand. */
export function useSeriesList() {
  const items = ref<Series[]>([]);
  // Start true so the first paint shows a loader, not a false "empty" message.
  const loading = ref(true);
  const failed = ref(false);
  const done = ref(false);
  const cursor = ref<string | null>(null);
  let params: SeriesQuery = {};
  let started = false; // no paging until the first reload sets a real query

  async function fetchPage(reset: boolean): Promise<void> {
    if (loading.value && started && !reset) return;
    loading.value = true;
    const query: SeriesQuery = { ...params, limit: 24 };
    if (!reset && cursor.value) query.cursor = cursor.value;
    const { data, error } = await api.GET("/api/series", { params: { query } });
    if (!error && data) {
      const mapped = data.items.map(toSeries);
      items.value = reset ? mapped : [...items.value, ...mapped];
      cursor.value = data.nextCursor ?? null;
      done.value = !data.nextCursor;
      failed.value = false;
    } else if (reset) {
      failed.value = true; // distinguish a load failure from a genuinely empty grid
      items.value = [];
    }
    loading.value = false;
  }

  async function reload(next: SeriesQuery): Promise<void> {
    started = true;
    params = next;
    cursor.value = null;
    done.value = false;
    failed.value = false;
    // Stale-while-revalidate: keep previous items visible until the new page lands
    // so tab/filter changes don't flash an empty grid.
    loading.value = true;
    await fetchPage(true);
  }

  function loadMore(): void {
    // Never before the first reload — otherwise the sentinel fetches an unfiltered
    // page 1 (empty params) and briefly flashes the wrong series on navigation.
    if (started && !done.value && !loading.value) void fetchPage(false);
  }

  function retry(): void {
    void fetchPage(true);
  }

  return { items, loading, failed, hasMore: computed(() => !done.value), reload, loadMore, retry };
}

// --- series detail -------------------------------------------------------------

export async function patchSeries(id: string, body: SeriesUpdate): Promise<void> {
  await api.PATCH("/api/series/{series_id}", { params: { path: { series_id: id } }, body });
}

export interface MatchCandidate {
  providerSeriesId: string;
  title: string;
  year: number | null;
  status: string | null;
  coverUrl: string | null;
}

export async function fetchMatchCandidates(id: string, q?: string): Promise<MatchCandidate[]> {
  const { data, error } = await api.GET("/api/series/{series_id}/match-candidates", {
    params: { path: { series_id: id }, query: q ? { q } : {} },
  });
  if (error || !data) return [];
  return data.map((d) => ({
    providerSeriesId: d.providerSeriesId,
    title: d.title,
    year: d.year ?? null,
    status: d.status ?? null,
    coverUrl: d.coverUrl ?? null,
  }));
}

/** Link a series to a provider entry (runs a background metadata fetch). */
export async function matchSeries(
  id: string,
  providerSeriesId: string,
  provider = "mangadex",
): Promise<void> {
  await api.POST("/api/series/{series_id}/match", {
    params: { path: { series_id: id } },
    body: { providerSeriesId, provider },
  });
}

/** Re-fetch provider metadata for an already-matched series (background task). */
export async function refreshSeries(id: string): Promise<void> {
  await api.POST("/api/series/{series_id}/refresh", { params: { path: { series_id: id } } });
}

export async function unlinkMatch(id: string): Promise<void> {
  await api.DELETE("/api/series/{series_id}/match", { params: { path: { series_id: id } } });
}

export async function fetchSeries(id: string): Promise<Series> {
  const { data, error } = await api.GET("/api/series/{series_id}", {
    params: { path: { series_id: id } },
  });
  if (error || !data) throw new Error("Series not found");
  return toSeries(data);
}

export async function fetchChapters(id: string): Promise<VolumeGroup[]> {
  const { data, error } = await api.GET("/api/series/{series_id}/chapters", {
    params: { path: { series_id: id } },
  });
  if (error || !data) return [];
  return data.map((group) => ({
    volume: group.volume,
    chapters: group.chapters.map(toChapter),
  }));
}

export interface ChapterDetail {
  id: string;
  seriesId: string;
  volume: number | null;
  number: string;
  title?: string;
  pageCount: number;
}

export async function fetchChapterDetail(id: string): Promise<ChapterDetail> {
  const { data, error } = await api.GET("/api/chapters/{chapter_id}", {
    params: { path: { chapter_id: id } },
  });
  if (error || !data) throw new Error("Chapter not found");
  return {
    id: data.id,
    seriesId: data.seriesId,
    volume: data.volume,
    number: data.number,
    title: data.title ?? undefined,
    pageCount: data.pageCount,
  };
}

export async function putProgress(
  chapterId: string,
  page: number,
  completed?: boolean,
): Promise<void> {
  await api.PUT("/api/chapters/{chapter_id}/progress", {
    params: { path: { chapter_id: chapterId } },
    body: { page, completed },
  });
}

export async function fetchRelated(id: string): Promise<Series[]> {
  const { data, error } = await api.GET("/api/series/{series_id}/related", {
    params: { path: { series_id: id } },
  });
  if (error || !data) return [];
  return data.map(toSeries);
}

export async function fetchArt(id: string): Promise<string[]> {
  const { data, error } = await api.GET("/api/series/{series_id}/art", {
    params: { path: { series_id: id } },
  });
  if (error || !data) return [];
  return data.images;
}

// --- gallery -------------------------------------------------------------------

/** All gallery-kind series (few enough to filter client-side + derive facets). */
export async function fetchCollection(id: string): Promise<{ name: string; series: Series[] } | null> {
  const { data, error } = await api.GET("/api/collections/{collection_id}", {
    params: { path: { collection_id: id } },
  });
  if (error || !data) return null;
  return { name: data.name, series: data.series.map(toSeries) };
}

export async function fetchGalleries(): Promise<Series[]> {
  const { data, error } = await api.GET("/api/series", {
    params: { query: { kind: "gallery", limit: 100, sort: "recentlyAdded" } },
  });
  if (error || !data) return [];
  return data.items.map(toSeries);
}

/** Every media item of a gallery (follows the cursor to the end). */
export async function fetchGalleryImages(id: string): Promise<import("../types").GalleryMediaItem[]> {
  const items: import("../types").GalleryMediaItem[] = [];
  let cursor: string | undefined;
  do {
    const { data, error } = await api.GET("/api/series/{series_id}/images", {
      params: { path: { series_id: id }, query: { limit: 100, ...(cursor ? { cursor } : {}) } },
    });
    if (error || !data) break;
    for (const row of data.items) {
      items.push({
        index: row.index,
        kind: row.kind as import("../types").GalleryMediaKind,
        url: row.url,
        thumbUrl: row.thumbUrl,
        posterUrl: row.posterUrl ?? null,
      });
    }
    cursor = data.nextCursor ?? undefined;
  } while (cursor);
  return items;
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
