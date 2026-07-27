// MSW request handlers for every endpoint the frontend calls (see
// frontend/AGENTS.md → "Mock harness"). Backed by the mutable in-memory
// fixtures under mocks/data/ so create/update/delete flows behave like a real
// (if small) backend across the lifetime of a dev session.

import { delay, http, HttpResponse } from "msw";

import type { components } from "../api/schema";
import { kindFor } from "./data/collections";
import { collectionsDb } from "./data/collections";
import {
  applyProgress,
  chapterById,
  chaptersDb,
  deleteChapterRow,
  volumeGroupsFor,
  type MockChapter,
} from "./data/chapters";
import { providersDb, trackersDb } from "./data/integrations";
import { librariesDb, librarySummaryDb } from "./data/libraries";
import {
  buildAbout,
  fsMkdir,
  fsParentOf,
  fsRoot,
  fsTree,
  importConfig,
  syncState,
} from "./data/settings";
import { downloadsDb, nextDownloadId } from "./data/downloads";
import { seriesCatalog } from "./data/series";
import {
  addTaxonomyDef,
  buildTaxonomyItems,
  removeTaxonomyDef,
  setTaxonomyEnabled,
  tag as taxonomyTag,
} from "./data/taxonomy";
import { coverSvg, galleryImageSvg, pageSvg, svgResponseInit } from "./images";
import { simulateTask, subscribeTaskStream } from "./taskBus";
import { decodeCursorOffset, encodeCursor, nowIso, pick, randInt, rngFor, slugify } from "./utils";

type SeriesOut = components["schemas"]["SeriesOut"];
type ChapterOut = components["schemas"]["ChapterOut"];
type TaskOut = components["schemas"]["TaskOut"];
type DownloadTaskOut = components["schemas"]["DownloadTaskOut"];
type LibraryOut = components["schemas"]["LibraryOut"];

function apiError(status: number, code: string, message: string) {
  return HttpResponse.json({ error: { code, message } }, { status });
}

function seriesById(id: string): SeriesOut | undefined {
  return seriesCatalog.find((s) => s.id === id);
}

function toChapterOut(c: MockChapter): ChapterOut {
  return {
    id: c.id,
    volume: c.volume,
    number: c.number,
    title: c.title ?? null,
    group: c.group ?? null,
    language: c.language,
    uploadedAt: c.uploadedAt,
    read: c.read,
    comments: c.comments,
    status: c.status,
    providerChapterId: c.providerChapterId ?? null,
  };
}

// --- /api/series filtering/sorting -----------------------------------------

function matchesTags(series: SeriesOut, tagsParam: string | null, tagMode: string | null): boolean {
  if (!tagsParam) return true;
  const parts = tagsParam.split(",").filter(Boolean);
  const include = parts.filter((p) => !p.startsWith("-"));
  const exclude = parts.filter((p) => p.startsWith("-")).map((p) => p.slice(1));
  const ids = new Set(series.tags.map((t) => t.id));
  if (exclude.some((id) => ids.has(id))) return false;
  if (include.length === 0) return true;
  return tagMode === "or" ? include.some((id) => ids.has(id)) : include.every((id) => ids.has(id));
}

function matchesCsv(value: string, csv: string | null): boolean {
  if (!csv) return true;
  return csv.split(",").filter(Boolean).includes(value);
}

function matchesReadState(series: SeriesOut, readState: string | null): boolean {
  if (!readState) return true;
  const started = (series.lastReadChapter ?? 0) > 0;
  if (readState === "read") return series.chapterCount > 0 && series.unreadCount === 0;
  if (readState === "in_progress") return started && series.unreadCount > 0;
  if (readState === "unread") return !started && series.unreadCount > 0;
  return true;
}

function sortSeriesList(list: SeriesOut[], sort: string | null): SeriesOut[] {
  const arr = [...list];
  switch (sort) {
    case "title":
      return arr.sort((a, b) => a.title.localeCompare(b.title));
    case "rating":
      return arr.sort((a, b) => (b.rating ?? 0) - (a.rating ?? 0));
    case "unread":
      return arr.sort((a, b) => b.unreadCount - a.unreadCount);
    case "recentlyUpdated":
      return arr.sort(
        (a, b) => new Date(b.chaptersSyncedAt ?? 0).getTime() - new Date(a.chaptersSyncedAt ?? 0).getTime(),
      );
    default:
      return arr; // recentlyAdded: catalog insertion order
  }
}

function filterSeries(url: URL): SeriesOut[] {
  const q = url.searchParams;
  return seriesCatalog.filter((s) => {
    if (q.get("kind") && s.kind !== q.get("kind")) return false;
    if (q.get("shelf") && s.libraryStatus !== q.get("shelf")) return false;
    if (q.get("favorite") === "true" && !s.favorite) return false;
    if (q.get("favorite") === "false" && s.favorite) return false;
    if (q.get("q") && !s.title.toLowerCase().includes(q.get("q")!.toLowerCase())) return false;
    if (!matchesTags(s, q.get("tags"), q.get("tagMode"))) return false;
    if (!matchesCsv(s.contentRating, q.get("ratings"))) return false;
    if (!matchesCsv(s.demographic, q.get("demographics"))) return false;
    if (!matchesCsv(s.status, q.get("pubStatus"))) return false;
    if (!matchesReadState(s, q.get("readState"))) return false;
    if (q.get("artist") && !s.artists.some((a) => a.toLowerCase().includes(q.get("artist")!.toLowerCase())))
      return false;
    if (q.get("source") && !(s.source ?? "").toLowerCase().includes(q.get("source")!.toLowerCase())) return false;
    return true;
  });
}

// --- updates feed (derived from chapter upload timestamps) ------------------

function recentUpdates(unreadOnly: boolean, limit: number) {
  const rows = unreadOnly ? chaptersDb.filter((c) => !c.read) : chaptersDb;
  return [...rows]
    .sort((a, b) => new Date(b.uploadedAt).getTime() - new Date(a.uploadedAt).getTime())
    .slice(0, limit)
    .map((c) => {
      const series = seriesById(c.seriesId);
      return series ? { series, volume: c.volume, chapter: c.number, updatedAt: c.uploadedAt } : null;
    })
    .filter((u): u is NonNullable<typeof u> => u !== null);
}

// --- download simulation ----------------------------------------------------

function simulateDownload(row: DownloadTaskOut): TaskOut {
  row.status = "downloading";
  row.phase = "fetching";
  return simulateTask({
    kind: "download",
    label: `Downloading ${row.series.title} — ${row.chapter}`,
    steps: 6,
    stepDelayMs: 500,
    detailForStep: (_step, progress) => `${Math.round((progress / 100) * 40)}/40 pages`,
    onProgress: (task) => {
      if (row.status === "paused") return;
      row.progress = task.progress;
      row.phase = task.progress < 60 ? "fetching" : "encoding";
      row.detail = task.detail ?? row.detail;
    },
    onDone: () => {
      if (row.status === "paused") return;
      row.status = "done";
      row.progress = 100;
      row.phase = null;
      row.detail = null;
      row.sizeBytes = randInt(rngFor(row.id), 4_000_000, 42_000_000);
    },
  });
}

export const handlers = [
  http.get("/api/health", () => HttpResponse.json({ status: "ok" })),

  // --- series -----------------------------------------------------------
  http.get("/api/series", async ({ request }) => {
    await delay(120);
    const url = new URL(request.url);
    const filtered = sortSeriesList(filterSeries(url), url.searchParams.get("sort"));
    const limit = Number(url.searchParams.get("limit") ?? 24);
    const offset = decodeCursorOffset(url.searchParams.get("cursor"));
    const items = filtered.slice(offset, offset + limit);
    const nextCursor = offset + limit < filtered.length ? encodeCursor(offset + limit) : null;
    return HttpResponse.json({ items, nextCursor });
  }),

  http.get("/api/series/:series_id", async ({ params }) => {
    const series = seriesById(params.series_id as string);
    if (!series) return apiError(404, "series_not_found", "Series not found.");
    await delay(100);
    return HttpResponse.json(series);
  }),

  http.patch("/api/series/:series_id", async ({ params, request }) => {
    const series = seriesById(params.series_id as string);
    if (!series) return apiError(404, "series_not_found", "Series not found.");
    const body = (await request.json()) as components["schemas"]["SeriesUpdate"];
    if (body.favorite !== undefined && body.favorite !== null) series.favorite = body.favorite;
    if (body.libraryStatus !== undefined) series.libraryStatus = body.libraryStatus;
    if (body.rating !== undefined) series.userRating = body.rating;
    if (body.title !== undefined && body.title !== null) series.title = body.title;
    if (body.description !== undefined) series.description = body.description;
    if (body.year !== undefined) series.year = body.year;
    if (body.status !== undefined && body.status !== null) series.status = body.status;
    if (body.contentRating !== undefined && body.contentRating !== null) series.contentRating = body.contentRating;
    if (body.demographic !== undefined && body.demographic !== null) series.demographic = body.demographic;
    if (body.originCountry !== undefined) series.originCountry = body.originCountry;
    if (body.authors !== undefined && body.authors !== null) series.authors = body.authors;
    if (body.artists !== undefined && body.artists !== null) series.artists = body.artists;
    if (body.tagIds !== undefined && body.tagIds !== null) series.tags = body.tagIds.map(taxonomyTag);
    if (body.source !== undefined) series.source = body.source;
    if (body.characters !== undefined) series.characters = body.characters;
    await delay(150);
    return HttpResponse.json(series);
  }),

  http.post("/api/series/:series_id/refresh", async ({ params }) => {
    const series = seriesById(params.series_id as string);
    if (!series) return apiError(404, "series_not_found", "Series not found.");
    const task = simulateTask({
      kind: "metadata",
      label: `Refreshing ${series.title}`,
      onDone: () => {
        series.chaptersSyncedAt = nowIso();
      },
    });
    return HttpResponse.json(task, { status: 202 });
  }),

  http.get("/api/series/:series_id/match-candidates", async ({ params, request }) => {
    const series = seriesById(params.series_id as string);
    if (!series) return apiError(404, "series_not_found", "Series not found.");
    const url = new URL(request.url);
    const q = url.searchParams.get("q") ?? series.title;
    await delay(300);
    const rng = rngFor(`${series.id}-candidates`);
    const candidates = Array.from({ length: randInt(rng, 3, 5) }, (_, i) => ({
      providerSeriesId: `md-${slugify(q)}-${i}`,
      title: i === 0 ? q : `${q} ${pick(rng, ["(Official)", "— Season 2", "(Colored)", "Redux"])}`,
      year: randInt(rng, 2005, 2024),
      status: pick(rng, ["ongoing", "completed", "hiatus"]),
      coverUrl: `/api/series/${series.id}/cover?variant=candidate&n=${i}`,
    }));
    return HttpResponse.json(candidates);
  }),

  http.post("/api/series/:series_id/match", async ({ params, request }) => {
    const series = seriesById(params.series_id as string);
    if (!series) return apiError(404, "series_not_found", "Series not found.");
    const body = (await request.json()) as components["schemas"]["MatchRequest"];
    const task = simulateTask({
      kind: "metadata",
      label: `Matching ${series.title}`,
      onDone: () => {
        series.provider = body.provider || "mangadex";
        series.chaptersSyncedAt = nowIso();
        series.availableChapters += randInt(rngFor(series.id + "-match"), 1, 4);
      },
    });
    return HttpResponse.json(task, { status: 202 });
  }),

  http.delete("/api/series/:series_id/match", async ({ params }) => {
    const series = seriesById(params.series_id as string);
    if (!series) return apiError(404, "series_not_found", "Series not found.");
    series.provider = null;
    series.chaptersSyncedAt = null;
    await delay(150);
    return new HttpResponse(null, { status: 204 });
  }),

  http.get("/api/series/:series_id/chapters", async ({ params, request }) => {
    const series = seriesById(params.series_id as string);
    if (!series) return apiError(404, "series_not_found", "Series not found.");
    const url = new URL(request.url);
    const language = url.searchParams.get("language") || undefined;
    const order = (url.searchParams.get("order") as "asc" | "desc" | null) ?? undefined;
    await delay(120);
    const groups = volumeGroupsFor(series.id, { language, order }).map((g) => ({
      volume: g.volume,
      chapters: g.chapters.map(toChapterOut),
    }));
    return HttpResponse.json(groups);
  }),

  http.get("/api/series/:series_id/related", async ({ params }) => {
    const series = seriesById(params.series_id as string);
    if (!series) return apiError(404, "series_not_found", "Series not found.");
    const tagIds = new Set(series.tags.map((t) => t.id));
    await delay(120);
    const related = seriesCatalog
      .filter((s) => s.id !== series.id && s.kind === series.kind)
      .map((s) => ({ s, overlap: s.tags.filter((t) => tagIds.has(t.id)).length }))
      .sort((a, b) => b.overlap - a.overlap)
      .slice(0, 10)
      .map((x) => x.s);
    return HttpResponse.json(related);
  }),

  http.get("/api/series/:series_id/art", async ({ params }) => {
    const series = seriesById(params.series_id as string);
    if (!series) return apiError(404, "series_not_found", "Series not found.");
    await delay(120);
    if (!series.provider) return HttpResponse.json({ images: [] });
    const rng = rngFor(`${series.id}-art`);
    const count = randInt(rng, 3, 6);
    const images = Array.from(
      { length: count },
      (_, i) => `/api/series/${series.id}/cover?variant=art&n=${i}`,
    );
    return HttpResponse.json({ images });
  }),

  http.get("/api/series/:series_id/images", async ({ params, request }) => {
    const series = seriesById(params.series_id as string);
    if (!series || !series.imageCount) return apiError(404, "series_not_found", "Gallery not found.");
    const url = new URL(request.url);
    const limit = Number(url.searchParams.get("limit") ?? 100);
    const offset = decodeCursorOffset(url.searchParams.get("cursor"));
    await delay(150);
    const end = Math.min(series.imageCount, offset + limit);
    const items = [];
    for (let index = offset; index < end; index++) {
      const kind = index % 15 === 14 ? "video" : index % 6 === 5 ? "gif" : "image";
      items.push({
        index,
        kind,
        url: `/api/series/${series.id}/images/${index}`,
        thumbUrl: `/api/series/${series.id}/images/${index}/thumb`,
        posterUrl: kind === "video" ? `/api/series/${series.id}/images/${index}/poster` : null,
      });
    }
    const nextCursor = end < series.imageCount ? encodeCursor(end) : null;
    return HttpResponse.json({ items, nextCursor });
  }),

  // --- binary image endpoints --------------------------------------------
  http.get("/api/series/:series_id/cover", ({ params, request }) => {
    const series = seriesById(params.series_id as string);
    if (!series) return apiError(404, "series_not_found", "Series not found.");
    const url = new URL(request.url);
    const size = url.searchParams.get("size") ?? "cover";
    const variant = url.searchParams.get("variant");
    const n = url.searchParams.get("n") ?? "0";
    const [w, h] = size === "detail" ? [600, 840] : [400, 560];
    const seed = variant ? `${series.id}:${variant}:${n}` : series.id;
    return new HttpResponse(coverSvg(seed, series.title, w, h), svgResponseInit());
  }),

  http.get("/api/series/:series_id/images/:index/thumb", ({ params }) => {
    const series = seriesById(params.series_id as string);
    if (!series) return apiError(404, "series_not_found", "Series not found.");
    const index = Number(params.index);
    const kind = index % 15 === 14 ? "video" : index % 6 === 5 ? "gif" : "image";
    return new HttpResponse(galleryImageSvg(series.id, kind, index, 320, 420), svgResponseInit());
  }),

  http.get("/api/series/:series_id/images/:index/poster", ({ params }) => {
    const series = seriesById(params.series_id as string);
    if (!series) return apiError(404, "series_not_found", "Series not found.");
    const index = Number(params.index);
    return new HttpResponse(galleryImageSvg(series.id, "video", index, 900, 1200), svgResponseInit());
  }),

  http.get("/api/series/:series_id/images/:index", ({ params }) => {
    const series = seriesById(params.series_id as string);
    if (!series) return apiError(404, "series_not_found", "Series not found.");
    const index = Number(params.index);
    const kind = index % 15 === 14 ? "video" : index % 6 === 5 ? "gif" : "image";
    return new HttpResponse(galleryImageSvg(series.id, kind, index, 900, 1200), svgResponseInit());
  }),

  http.get("/api/chapters/:chapter_id/pages/:n", ({ params }) => {
    const chapter = chapterById(params.chapter_id as string);
    if (!chapter) return apiError(404, "chapter_not_found", "Chapter not found.");
    const series = seriesById(chapter.seriesId);
    const page = Number(params.n);
    const label = `${series?.title ?? "Unknown"} — Ch. ${chapter.number}`;
    return new HttpResponse(pageSvg(chapter.id ?? chapter.seriesId, label, page, chapter.pageCount), svgResponseInit());
  }),

  // --- chapters -----------------------------------------------------------
  http.get("/api/chapters/:chapter_id", async ({ params }) => {
    const chapter = chapterById(params.chapter_id as string);
    if (!chapter) return apiError(404, "chapter_not_found", "Chapter not found.");
    await delay(100);
    return HttpResponse.json({
      id: chapter.id,
      seriesId: chapter.seriesId,
      volume: chapter.volume,
      number: chapter.number,
      title: chapter.title ?? null,
      group: chapter.group ?? null,
      language: chapter.language,
      pageCount: chapter.pageCount,
      comments: chapter.comments,
      read: chapter.read,
      uploadedAt: chapter.uploadedAt,
    });
  }),

  http.delete("/api/chapters/:chapter_id", async ({ params }) => {
    const result = deleteChapterRow(params.chapter_id as string);
    if (!result) return apiError(404, "chapter_not_found", "Chapter not found.");
    await delay(200);
    return HttpResponse.json(result);
  }),

  http.put("/api/chapters/:chapter_id/progress", async ({ params, request }) => {
    const body = (await request.json()) as components["schemas"]["ProgressUpdate"];
    applyProgress(params.chapter_id as string, body.completed);
    await delay(60);
    return new HttpResponse(null, { status: 204 });
  }),

  // --- dashboard / updates / search ---------------------------------------
  http.get("/api/dashboard", async () => {
    await delay(150);
    const continueReading = seriesCatalog.filter(
      (s) => s.libraryStatus === "reading" || s.libraryStatus === "re_reading",
    );
    return HttpResponse.json({
      stats: {
        series: seriesCatalog.length,
        unreadChapters: seriesCatalog.reduce((sum, s) => sum + s.unreadCount, 0),
        reading: continueReading.length,
      },
      continueReading: continueReading.slice(0, 12),
      recentUpdates: recentUpdates(false, 8),
      recentlyAdded: seriesCatalog.slice(0, 12),
    });
  }),

  http.get("/api/libraries/summary", async () => {
    await delay(80);
    return HttpResponse.json(librarySummaryDb);
  }),

  http.get("/api/updates", async ({ request }) => {
    const url = new URL(request.url);
    const limit = Number(url.searchParams.get("limit") ?? 60);
    await delay(150);
    return HttpResponse.json({ items: recentUpdates(false, limit), nextCursor: null });
  }),

  http.get("/api/updates/unread", async ({ request }) => {
    const url = new URL(request.url);
    const limit = Number(url.searchParams.get("limit") ?? 60);
    await delay(150);
    return HttpResponse.json({ items: recentUpdates(true, limit), nextCursor: null });
  }),

  http.get("/api/search", async ({ request }) => {
    const url = new URL(request.url);
    const q = (url.searchParams.get("q") ?? "").toLowerCase();
    const limit = Number(url.searchParams.get("limit") ?? 30);
    await delay(100);
    if (!q) return HttpResponse.json([]);
    const results = seriesCatalog.filter((s) => s.title.toLowerCase().includes(q)).slice(0, limit);
    return HttpResponse.json(results);
  }),

  // --- taxonomy -------------------------------------------------------------
  http.get("/api/taxonomy", async ({ request }) => {
    const url = new URL(request.url);
    const pageSize = Number(url.searchParams.get("pageSize") ?? 500);
    const page = Number(url.searchParams.get("page") ?? 1);
    await delay(80);
    const all = buildTaxonomyItems(seriesCatalog);
    const start = (page - 1) * pageSize;
    return HttpResponse.json({ items: all.slice(start, start + pageSize), total: all.length, page, pageSize });
  }),

  http.post("/api/taxonomy", async ({ request }) => {
    const body = (await request.json()) as components["schemas"]["TaxonomyCreate"];
    const id = `${body.category}-${slugify(body.name)}`;
    addTaxonomyDef({ id, name: body.name, category: body.category, system: false });
    await delay(150);
    return HttpResponse.json({ id, name: body.name, category: body.category, uses: 0, enabled: true, system: false }, { status: 201 });
  }),

  http.post("/api/taxonomy/refresh", async () => {
    const task = simulateTask({
      kind: "taxonomy",
      label: "Refreshing tag vocabulary from MangaDex",
      steps: 3,
      result: { newTags: 1 },
      onDone: () => {
        if (!buildTaxonomyItems(seriesCatalog).some((t) => t.id === "theme-urban-fantasy")) {
          addTaxonomyDef({ id: "theme-urban-fantasy", name: "Urban Fantasy", category: "theme", system: false });
        }
      },
    });
    return HttpResponse.json(task, { status: 202 });
  }),

  http.patch("/api/taxonomy/:tag_id", async ({ params, request }) => {
    const id = params.tag_id as string;
    const body = (await request.json()) as components["schemas"]["TaxonomyUpdate"];
    if (body.enabled !== undefined && body.enabled !== null) setTaxonomyEnabled(id, body.enabled);
    await delay(100);
    const item = buildTaxonomyItems(seriesCatalog).find((t) => t.id === id);
    if (!item) return apiError(404, "tag_not_found", "Tag not found.");
    return HttpResponse.json(item);
  }),

  http.delete("/api/taxonomy/:tag_id", async ({ params }) => {
    const removed = removeTaxonomyDef(params.tag_id as string);
    if (!removed) return apiError(404, "tag_not_found", "Only custom tags can be deleted.");
    await delay(100);
    return new HttpResponse(null, { status: 204 });
  }),

  // --- libraries --------------------------------------------------------
  http.get("/api/libraries", async () => {
    await delay(80);
    return HttpResponse.json(librariesDb);
  }),

  http.post("/api/libraries", async ({ request }) => {
    const body = (await request.json()) as components["schemas"]["LibraryCreate"];
    const created: LibraryOut = {
      id: `lib-${slugify(body.name)}-${librariesDb.length + 1}`,
      name: body.name,
      path: body.path,
      kind: body.kind || "manga",
      enabled: true,
      seriesCount: 0,
      lastScan: null,
    };
    librariesDb.push(created);
    await delay(200);
    return HttpResponse.json(created, { status: 201 });
  }),

  http.post("/api/libraries/scan", async () => {
    const task = simulateTask({
      kind: "scan",
      label: "Scanning all libraries",
      steps: 5,
      onDone: () => {
        for (const lib of librariesDb) if (lib.enabled) lib.lastScan = nowIso();
      },
    });
    return HttpResponse.json(task, { status: 202 });
  }),

  http.patch("/api/libraries/:library_id", async ({ params, request }) => {
    const lib = librariesDb.find((l) => l.id === params.library_id);
    if (!lib) return apiError(404, "library_not_found", "Library not found.");
    const body = (await request.json()) as components["schemas"]["LibraryUpdate"];
    if (body.name !== undefined && body.name !== null) lib.name = body.name;
    if (body.path !== undefined && body.path !== null) lib.path = body.path;
    if (body.enabled !== undefined && body.enabled !== null) lib.enabled = body.enabled;
    await delay(150);
    return HttpResponse.json(lib);
  }),

  http.delete("/api/libraries/:library_id", async ({ params }) => {
    const idx = librariesDb.findIndex((l) => l.id === params.library_id);
    if (idx === -1) return apiError(404, "library_not_found", "Library not found.");
    librariesDb.splice(idx, 1);
    await delay(150);
    return new HttpResponse(null, { status: 204 });
  }),

  http.post("/api/libraries/:library_id/scan", async ({ params }) => {
    const lib = librariesDb.find((l) => l.id === params.library_id);
    if (!lib) return apiError(404, "library_not_found", "Library not found.");
    const task = simulateTask({
      kind: "scan",
      label: `Scanning ${lib.name}`,
      steps: 4,
      onDone: () => {
        lib.lastScan = nowIso();
        if (lib.kind === "gallery") {
          simulateTask({
            kind: "thumbs",
            label: `Generating thumbnails for ${lib.name}`,
            steps: 3,
            result: { thumbsGenerated: randInt(rngFor(lib.id + nowIso()), 20, 400) },
          });
        }
      },
    });
    return HttpResponse.json(task, { status: 202 });
  }),

  // --- providers ----------------------------------------------------------
  http.get("/api/providers", async () => {
    await delay(80);
    return HttpResponse.json(providersDb);
  }),

  http.patch("/api/providers/:provider_id", async ({ params, request }) => {
    const provider = providersDb.find((p) => p.id === params.provider_id);
    if (!provider) return apiError(404, "provider_not_found", "Provider not found.");
    const body = (await request.json()) as components["schemas"]["ProviderUpdate"];
    if (body.enabled !== undefined && body.enabled !== null) provider.enabled = body.enabled;
    if (body.language !== undefined && body.language !== null) provider.language = body.language;
    if (body.autoMatch !== undefined && body.autoMatch !== null) provider.autoMatch = body.autoMatch;
    if (body.fetchCovers !== undefined && body.fetchCovers !== null) provider.fetchCovers = body.fetchCovers;
    if (body.dataSaver !== undefined && body.dataSaver !== null) provider.dataSaver = body.dataSaver;
    await delay(150);
    return HttpResponse.json(provider);
  }),

  http.post("/api/providers/:provider_id/connect", async ({ params, request }) => {
    const provider = providersDb.find((p) => p.id === params.provider_id);
    if (!provider) return apiError(404, "provider_not_found", "Provider not found.");
    const body = (await request.json()) as components["schemas"]["ProviderConnect"];
    provider.connected = true;
    provider.accountName = body.username;
    await delay(400);
    return HttpResponse.json(provider);
  }),

  http.post("/api/providers/:provider_id/disconnect", async ({ params }) => {
    const provider = providersDb.find((p) => p.id === params.provider_id);
    if (!provider) return apiError(404, "provider_not_found", "Provider not found.");
    provider.connected = false;
    provider.accountName = null;
    await delay(150);
    return HttpResponse.json(provider);
  }),

  http.post("/api/providers/:provider_id/sync", async ({ params }) => {
    const provider = providersDb.find((p) => p.id === params.provider_id);
    if (!provider) return apiError(404, "provider_not_found", "Provider not found.");
    const task = simulateTask({
      kind: "import",
      label: `Syncing ${provider.name} account`,
      steps: 4,
      result: { synced: randInt(rngFor(provider.id + nowIso()), 2, 15) },
    });
    return HttpResponse.json(task, { status: 202 });
  }),

  // --- trackers -------------------------------------------------------------
  http.get("/api/trackers", async () => {
    await delay(80);
    return HttpResponse.json(trackersDb);
  }),

  http.patch("/api/trackers/:tracker_id", async ({ params, request }) => {
    const tracker = trackersDb.find((t) => t.id === params.tracker_id);
    if (!tracker) return apiError(404, "tracker_not_found", "Tracker not found.");
    const body = (await request.json()) as components["schemas"]["TrackerUpdate"];
    if (body.syncOnRead !== undefined && body.syncOnRead !== null) tracker.syncOnRead = body.syncOnRead;
    await delay(120);
    return HttpResponse.json(tracker);
  }),

  http.delete("/api/trackers/:tracker_id", async ({ params }) => {
    const tracker = trackersDb.find((t) => t.id === params.tracker_id);
    if (!tracker) return apiError(404, "tracker_not_found", "Tracker not found.");
    tracker.connected = false;
    tracker.accountName = null;
    tracker.syncOnRead = false;
    await delay(150);
    return new HttpResponse(null, { status: 204 });
  }),

  http.post("/api/trackers/:tracker_id/connect", async ({ params }) => {
    const tracker = trackersDb.find((t) => t.id === params.tracker_id);
    if (!tracker) return apiError(404, "tracker_not_found", "Tracker not found.");
    await delay(200);
    return HttpResponse.json({
      authorizeUrl: `https://mock-tracker.invalid/oauth/authorize?tracker=${tracker.id}&state=${Date.now()}`,
    });
  }),

  http.post("/api/trackers/:tracker_id/callback", async ({ params }) => {
    const tracker = trackersDb.find((t) => t.id === params.tracker_id);
    if (!tracker) return apiError(404, "tracker_not_found", "Tracker not found.");
    tracker.connected = true;
    tracker.accountName = `dwi_${tracker.id}`;
    await delay(300);
    return HttpResponse.json(tracker);
  }),

  http.post("/api/trackers/:tracker_id/login", async ({ params, request }) => {
    const tracker = trackersDb.find((t) => t.id === params.tracker_id);
    if (!tracker) return apiError(404, "tracker_not_found", "Tracker not found.");
    const body = (await request.json()) as components["schemas"]["TrackerLogin"];
    tracker.connected = true;
    tracker.accountName = body.username;
    await delay(300);
    return HttpResponse.json(tracker);
  }),

  // --- sync -------------------------------------------------------------
  http.get("/api/sync", async () => {
    await delay(80);
    return HttpResponse.json(syncState);
  }),

  http.post("/api/sync", async () => {
    syncState.syncing = true;
    const task = simulateTask({
      kind: "sync",
      label: "Checking matched series for new chapters",
      steps: 5,
      onDone: (t) => {
        syncState.syncing = false;
        syncState.lastSync = nowIso();
        syncState.newChapters = (t.result?.newChapters as number | undefined) ?? randInt(rngFor(nowIso()), 0, 12);
      },
      result: { newChapters: randInt(rngFor("sync" + nowIso()), 0, 12) },
    });
    return HttpResponse.json(task, { status: 202 });
  }),

  // --- import -------------------------------------------------------------
  http.get("/api/import/config", async () => {
    await delay(80);
    return HttpResponse.json(importConfig);
  }),

  http.patch("/api/import/config", async ({ request }) => {
    const body = (await request.json()) as components["schemas"]["ImportConfigUpdate"];
    if (body.enabled !== undefined && body.enabled !== null) importConfig.enabled = body.enabled;
    if (body.quality !== undefined && body.quality !== null) importConfig.quality = body.quality;
    if (body.filenamePattern !== undefined && body.filenamePattern !== null)
      importConfig.filenamePattern = body.filenamePattern;
    if (body.patternPresets !== undefined && body.patternPresets !== null)
      importConfig.patternPresets = body.patternPresets;
    await delay(150);
    return HttpResponse.json(importConfig);
  }),

  http.post("/api/import", async ({ request }) => {
    const body = (await request.json()) as components["schemas"]["ImportRequest"];
    const task = simulateTask({ kind: "localimport", label: `Importing ${body.path}`, steps: 5 });
    return HttpResponse.json(task, { status: 202 });
  }),

  http.post("/api/import/upload", async () => {
    const task = simulateTask({ kind: "localimport", label: "Importing uploaded files", steps: 5 });
    return HttpResponse.json(task, { status: 202 });
  }),

  // --- about --------------------------------------------------------------
  http.get("/api/about", async () => {
    await delay(80);
    return HttpResponse.json(buildAbout());
  }),

  // --- collections ("lists") ----------------------------------------------
  http.get("/api/collections", async () => {
    await delay(100);
    return HttpResponse.json(collectionsDb);
  }),

  http.post("/api/collections", async ({ request }) => {
    const body = (await request.json()) as components["schemas"]["CollectionCreate"];
    const created = {
      id: `list-${slugify(body.name)}-${collectionsDb.length + 1}`,
      name: body.name,
      description: body.description ?? null,
      seriesIds: [],
      kind: null,
    };
    collectionsDb.push(created);
    await delay(150);
    return HttpResponse.json(created, { status: 201 });
  }),

  http.get("/api/collections/:collection_id", async ({ params }) => {
    const collection = collectionsDb.find((c) => c.id === params.collection_id);
    if (!collection) return apiError(404, "collection_not_found", "List not found.");
    await delay(120);
    const series = collection.seriesIds.map(seriesById).filter((s): s is SeriesOut => Boolean(s));
    return HttpResponse.json({ id: collection.id, name: collection.name, description: collection.description, series });
  }),

  http.patch("/api/collections/:collection_id", async ({ params, request }) => {
    const collection = collectionsDb.find((c) => c.id === params.collection_id);
    if (!collection) return apiError(404, "collection_not_found", "List not found.");
    const body = (await request.json()) as components["schemas"]["CollectionUpdate"];
    if (body.name !== undefined && body.name !== null) collection.name = body.name;
    if (body.description !== undefined) collection.description = body.description;
    await delay(120);
    return HttpResponse.json(collection);
  }),

  http.delete("/api/collections/:collection_id", async ({ params }) => {
    const idx = collectionsDb.findIndex((c) => c.id === params.collection_id);
    if (idx === -1) return apiError(404, "collection_not_found", "List not found.");
    collectionsDb.splice(idx, 1);
    await delay(120);
    return new HttpResponse(null, { status: 204 });
  }),

  http.post("/api/collections/:collection_id/series", async ({ params, request }) => {
    const collection = collectionsDb.find((c) => c.id === params.collection_id);
    if (!collection) return apiError(404, "collection_not_found", "List not found.");
    const body = (await request.json()) as components["schemas"]["CollectionSeriesAdd"];
    if (!collection.seriesIds.includes(body.seriesId)) collection.seriesIds.push(body.seriesId);
    collection.kind = kindFor(collection.seriesIds);
    await delay(100);
    return HttpResponse.json(collection);
  }),

  http.delete("/api/collections/:collection_id/series/:series_id", async ({ params }) => {
    const collection = collectionsDb.find((c) => c.id === params.collection_id);
    if (!collection) return apiError(404, "collection_not_found", "List not found.");
    collection.seriesIds = collection.seriesIds.filter((id) => id !== params.series_id);
    collection.kind = kindFor(collection.seriesIds);
    await delay(100);
    return new HttpResponse(null, { status: 204 });
  }),

  // --- tasks / events -------------------------------------------------------
  http.get("/api/tasks", () => HttpResponse.json([])),

  http.get("/api/events", () => {
    const encoder = new TextEncoder();
    let unsubscribe = () => {};
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(": connected\n\n"));
        unsubscribe = subscribeTaskStream(({ event, task }) => {
          controller.enqueue(encoder.encode(`data: ${JSON.stringify({ event, task })}\n\n`));
        });
      },
      cancel() {
        unsubscribe();
      },
    });
    return new HttpResponse(stream, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      },
    });
  }),

  // --- downloads --------------------------------------------------------
  http.get("/api/downloads", async () => {
    await delay(100);
    return HttpResponse.json(downloadsDb);
  }),

  http.post("/api/downloads", async ({ request }) => {
    const body = (await request.json()) as components["schemas"]["DownloadCreate"];
    await delay(150);

    if (body.action) {
      if (body.action === "pause-all") {
        for (const row of downloadsDb) if (row.status === "downloading" || row.status === "queued") row.status = "paused";
      } else if (body.action === "cancel-all") {
        for (let i = downloadsDb.length - 1; i >= 0; i--) {
          if (downloadsDb[i]?.status !== "done") downloadsDb.splice(i, 1);
        }
      } else if (body.action === "resume-all") {
        for (const row of downloadsDb) if (row.status === "paused") simulateDownload(row);
      }
      return HttpResponse.json(downloadsDb);
    }

    const series = body.seriesId ? seriesById(body.seriesId) : undefined;
    if (!series) return apiError(422, "invalid_request", "seriesId is required to queue a download.");
    const chapterLabel = body.providerChapterIds?.length
      ? `${body.providerChapterIds.length} chapter${body.providerChapterIds.length > 1 ? "s" : ""}`
      : (chaptersDb.find((c) => c.seriesId === series.id && c.status === "available")?.number ?? "New chapters");
    const row: DownloadTaskOut = {
      id: nextDownloadId(),
      series,
      chapter: chapterLabel.startsWith("New") ? chapterLabel : `Ch. ${chapterLabel}`,
      status: "queued",
      progress: 0,
      phase: null,
      detail: null,
      sizeBytes: null,
    };
    downloadsDb.push(row);
    setTimeout(() => simulateDownload(row), 400);
    return HttpResponse.json(row);
  }),

  http.post("/api/downloads/clear-completed", async () => {
    for (let i = downloadsDb.length - 1; i >= 0; i--) {
      if (downloadsDb[i]?.status === "done") downloadsDb.splice(i, 1);
    }
    await delay(100);
    return new HttpResponse(null, { status: 204 });
  }),

  http.post("/api/downloads/:task_id/retry", async ({ params }) => {
    const row = downloadsDb.find((d) => d.id === params.task_id);
    if (!row) return apiError(404, "download_not_found", "Download not found.");
    row.status = "queued";
    row.progress = 0;
    row.detail = null;
    const task = simulateTask({
      kind: "download",
      label: `Retrying ${row.series.title} — ${row.chapter}`,
      steps: 1,
      stepDelayMs: 300,
      onDone: () => simulateDownload(row),
    });
    return HttpResponse.json(task, { status: 202 });
  }),

  http.post("/api/downloads/:task_id/pause", async ({ params }) => {
    const row = downloadsDb.find((d) => d.id === params.task_id);
    if (!row) return apiError(404, "download_not_found", "Download not found.");
    row.status = "paused";
    await delay(100);
    return HttpResponse.json(downloadsDb);
  }),

  http.post("/api/downloads/:task_id/resume", async ({ params }) => {
    const row = downloadsDb.find((d) => d.id === params.task_id);
    if (!row) return apiError(404, "download_not_found", "Download not found.");
    simulateDownload(row);
    await delay(100);
    return HttpResponse.json(downloadsDb);
  }),

  http.delete("/api/downloads/:task_id", async ({ params }) => {
    const idx = downloadsDb.findIndex((d) => d.id === params.task_id);
    if (idx === -1) return apiError(404, "download_not_found", "Download not found.");
    downloadsDb.splice(idx, 1);
    await delay(100);
    return new HttpResponse(null, { status: 204 });
  }),

  // --- filesystem browser ---------------------------------------------------
  http.get("/api/fs", async ({ request }) => {
    const url = new URL(request.url);
    const path = url.searchParams.get("path") || fsRoot();
    await delay(100);
    return HttpResponse.json({ root: fsRoot(), path, parent: fsParentOf(path), entries: fsTree.get(path) ?? [] });
  }),

  http.post("/api/fs/mkdir", async ({ request }) => {
    const body = (await request.json()) as components["schemas"]["FsMkdir"];
    const entry = fsMkdir(body.parent, body.name);
    await delay(150);
    return HttpResponse.json(entry, { status: 201 });
  }),
];
