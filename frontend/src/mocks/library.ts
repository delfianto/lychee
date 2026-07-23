// Placeholder data so the UI renders before the API exists. Covers use picsum
// (dev only). Swap this module for the generated API client later.

import type { Chapter, RecentUpdate, Series, Tag, VolumeGroup } from "../types";

const tag = (id: string, name: string, group: Tag["group"]): Tag => ({ id, name, group });

const GENRES: Tag[] = [
  tag("action", "Action", "genre"),
  tag("drama", "Drama", "genre"),
  tag("comedy", "Comedy", "genre"),
  tag("romance", "Romance", "genre"),
  tag("fantasy", "Fantasy", "genre"),
  tag("slice", "Slice of Life", "genre"),
];

function cover(seed: string): string {
  return `https://picsum.photos/seed/${seed}/300/450`;
}

let n = 0;
function makeSeries(title: string, opts: Partial<Series> = {}): Series {
  n += 1;
  const id = `s${n}`;
  return {
    id,
    title,
    coverUrl: cover(id),
    authors: ["Author Name"],
    artists: ["Artist Name"],
    status: "ongoing",
    contentRating: "safe",
    demographic: "seinen",
    tags: GENRES.slice(0, 3),
    chapterCount: 120,
    unreadCount: 0,
    year: 2019,
    description:
      "A placeholder synopsis. Replace with real metadata once the scan pipeline and " +
      "MangaDex provider are wired up. It should truncate gracefully after a few lines, " +
      "expanding when the reader chooses to see more of the description.",
    ...opts,
  };
}

export const continueReading: Series[] = [
  makeSeries("Hanzawa Naoki", {
    unreadCount: 3,
    lastReadChapter: 45,
    totalChapters: 120,
    tags: [GENRES[1], GENRES[2]],
    demographic: "seinen",
  }),
  makeSeries("Blue Period", { unreadCount: 1, lastReadChapter: 58, totalChapters: 62 }),
  makeSeries("Vinland Saga", { unreadCount: 7, lastReadChapter: 190, totalChapters: 210 }),
];

export const librarySeries: Series[] = Array.from({ length: 18 }, (_, i) =>
  makeSeries(`Series Title ${i + 1}`, { unreadCount: i % 4 === 0 ? (i % 9) + 1 : 0 }),
);

export const recentUpdates: RecentUpdate[] = librarySeries.slice(0, 8).map((series, i) => ({
  series,
  chapterLabel: `Ch. ${series.chapterCount - (i % 3)}`,
  updatedAt: `${i + 1}h ago`,
}));

export function findSeries(id: string): Series {
  return [...continueReading, ...librarySeries].find((s) => s.id === id) ?? continueReading[0];
}

let chapNo = 210;
function makeChapter(volume: number, i: number): Chapter {
  const num = chapNo;
  chapNo -= 1;
  return {
    id: `c${num}`,
    volume,
    number: String(num),
    title: `Chapter title ${num}`,
    group: i % 2 === 0 ? "Scanlation Group" : "Official",
    language: "en",
    uploadedAt: `${i + 1}d ago`,
    read: num < 190,
    comments: (num * 7) % 40,
  };
}

export const mockVolumes: VolumeGroup[] = [3, 2, 1].map((vol) => ({
  volume: vol,
  chapters: Array.from({ length: 4 }, (_, i) => makeChapter(vol, i)),
}));
