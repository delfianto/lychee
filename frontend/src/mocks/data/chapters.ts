// Per-series chapter rows, derived from each series' chapterCount/availableChapters
// so the numbers agree everywhere (series card badge, chapter list, dashboard
// updates feed). Mutable — progress/delete handlers edit this array in place.

import type { components } from "../../api/schema";
import { chance, daysAgo, hoursAgo, pick, randInt, rngFor } from "../utils";
import { DOWNLOAD_DEMO_SERIES_IDS, seriesCatalog } from "./series";
import { SCANLATION_GROUPS } from "./names";

type SeriesOut = components["schemas"]["SeriesOut"];
export type ChapterStatus = "downloaded" | "available" | "queued" | "downloading" | "paused" | "failed";

export interface MockChapter {
  id: string | null;
  seriesId: string;
  volume: number | null;
  number: string;
  title?: string | null;
  group?: string | null;
  language: string;
  uploadedAt: string;
  read: boolean;
  comments: number;
  status: ChapterStatus;
  providerChapterId?: string | null;
  pageCount: number;
}

const CHAPTER_TITLE_FRAGMENTS = [
  "The Reckoning",
  "A Quiet Morning",
  "Into the Dark",
  "Turning Point",
  "First Blood",
  "The Long Way Home",
  "Falling Light",
  "What Remains",
  "No Turning Back",
  "The Space Between",
  "Old Wounds",
  "Aftermath",
];

const IN_FLIGHT_STATUSES: ChapterStatus[] = ["downloading", "queued", "paused", "failed"];

function isWebtoon(series: SeriesOut): boolean {
  return series.originCountry === "kr" || series.tags.some((t) => t.id === "format-long-strip" || t.id === "format-web-comic");
}

function buildChaptersForSeries(series: SeriesOut): MockChapter[] {
  if (series.kind !== "manga" && series.kind !== "comic") return [];
  const total = series.chapterCount + series.availableChapters;
  if (total <= 0) return [];

  const rng = rngFor(series.id);
  const webtoon = isWebtoon(series);
  const perVolume = randInt(rng, 7, 10);
  const primaryGroup = pick(rng, SCANLATION_GROUPS);
  const language = chance(rng, 0.1) ? pick(rng, ["ja", "es", "id"]) : "en";
  const cadenceDays = randInt(rng, 3, 10);
  const backfillFrom = series.status === "ongoing" ? 0 : randInt(rng, 30, 900);
  const demoIndex = DOWNLOAD_DEMO_SERIES_IDS.indexOf(series.id);

  const rows: MockChapter[] = [];
  for (let n = 1; n <= total; n++) {
    const downloaded = n <= series.chapterCount;
    const isInFlightSlot = !downloaded && demoIndex >= 0 && n === series.chapterCount + 1;
    const status: ChapterStatus = isInFlightSlot
      ? (IN_FLIGHT_STATUSES[demoIndex % IN_FLIGHT_STATUSES.length] ?? "downloading")
      : downloaded
        ? "downloaded"
        : "available";
    const ageDays = backfillFrom + (total - n) * cadenceDays;
    rows.push({
      id: downloaded ? `${series.id}-c${n}` : null,
      seriesId: series.id,
      volume: webtoon ? null : Math.ceil(n / perVolume),
      number: String(n),
      title: chance(rng, 0.25) ? pick(rng, CHAPTER_TITLE_FRAGMENTS) : null,
      group: series.provider ? primaryGroup : (chance(rng, 0.85) ? primaryGroup : pick(rng, SCANLATION_GROUPS)),
      language,
      uploadedAt: ageDays <= 0 ? hoursAgo(randInt(rng, 1, 20)) : daysAgo(ageDays),
      read: series.lastReadChapter != null && n <= series.lastReadChapter,
      comments: Math.round(Math.pow(rng(), 2) * 40),
      status,
      providerChapterId: series.provider ? `${series.id}-pc-${n}` : null,
      pageCount: randInt(rng, 16, 44),
    });
  }
  return rows;
}

export const chaptersDb: MockChapter[] = seriesCatalog.flatMap(buildChaptersForSeries);

export function chaptersFor(seriesId: string): MockChapter[] {
  return chaptersDb.filter((c) => c.seriesId === seriesId);
}

export function chapterById(chapterId: string): MockChapter | undefined {
  return chaptersDb.find((c) => c.id === chapterId);
}

export function volumeGroupsFor(
  seriesId: string,
  opts: { language?: string; order?: "asc" | "desc" } = {},
): { volume: number | null; chapters: MockChapter[] }[] {
  let rows = chaptersFor(seriesId);
  if (opts.language) rows = rows.filter((c) => c.language === opts.language);
  const byVolume = new Map<number | null, MockChapter[]>();
  for (const row of rows) {
    const list = byVolume.get(row.volume) ?? [];
    list.push(row);
    byVolume.set(row.volume, list);
  }
  const groups = [...byVolume.entries()].map(([volume, chapters]) => ({
    volume,
    chapters: chapters.sort((a, b) => Number(b.number) - Number(a.number)),
  }));
  groups.sort((a, b) => (b.volume ?? -Infinity) - (a.volume ?? -Infinity));
  if (opts.order === "asc") {
    groups.reverse();
    for (const g of groups) g.chapters.reverse();
  }
  return groups;
}

/** Mark a chapter's page progress; flips `read` (and the parent series' unread
 *  counters) once the reader reports the chapter as completed. */
export function applyProgress(chapterId: string, completed: boolean | null | undefined): void {
  const chapter = chapterById(chapterId);
  if (!chapter || !completed || chapter.read) return;
  chapter.read = true;
  const series = seriesCatalog.find((s) => s.id === chapter.seriesId);
  if (!series) return;
  series.unreadCount = Math.max(0, series.unreadCount - 1);
  const num = Number(chapter.number);
  if (!Number.isNaN(num)) series.lastReadChapter = Math.max(series.lastReadChapter ?? 0, num);
}

export interface DeleteChapterResult {
  mode: "provider" | "local";
  redownloadable: boolean;
  seriesId: string;
}

/** Remove local chapter content. Provider-matched chapters fall back to a
 *  remote-only row (re-downloadable); unmatched local-only chapters vanish. */
export function deleteChapterRow(chapterId: string): DeleteChapterResult | null {
  const idx = chaptersDb.findIndex((c) => c.id === chapterId);
  if (idx === -1) return null;
  const chapter = chaptersDb[idx];
  if (!chapter) return null;
  const series = seriesCatalog.find((s) => s.id === chapter.seriesId);
  const redownloadable = Boolean(series?.provider && chapter.providerChapterId);
  if (redownloadable) {
    chapter.id = null;
    chapter.status = "available";
  } else {
    chaptersDb.splice(idx, 1);
  }
  if (series) {
    series.chapterCount = Math.max(0, series.chapterCount - 1);
    if (!chapter.read) series.unreadCount = Math.max(0, series.unreadCount - 1);
    if (redownloadable) series.availableChapters += 1;
  }
  return {
    mode: redownloadable ? "provider" : "local",
    redownloadable,
    seriesId: chapter.seriesId,
  };
}
