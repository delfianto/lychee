// The download queue (Downloads settings panel) — a mix of states so every
// row style (progress bar, phase label, paused, failed, done) has a demo.

import type { components } from "../../api/schema";
import { seriesCatalog } from "./series";

type DownloadTaskOut = components["schemas"]["DownloadTaskOut"];

function seriesOrThrow(id: string) {
  const series = seriesCatalog.find((s) => s.id === id);
  if (!series) throw new Error(`downloads.ts: unknown series id ${id}`);
  return series;
}

let counter = 0;
function nextId(): string {
  counter += 1;
  return `dl-${counter}`;
}

export const downloadsDb: DownloadTaskOut[] = [
  {
    id: nextId(),
    series: seriesOrThrow("mecha-vandal-zero"),
    chapter: "Ch. 47",
    status: "downloading",
    progress: 62,
    phase: "fetching",
    detail: "24/40 pages",
    sizeBytes: null,
  },
  {
    id: nextId(),
    series: seriesOrThrow("bloodmoon-apothecary"),
    chapter: "Ch. 64",
    status: "downloading",
    progress: 88,
    phase: "encoding",
    detail: "35/40 pages",
    sizeBytes: null,
  },
  {
    id: nextId(),
    series: seriesOrThrow("nightfall-requiem"),
    chapter: "Ch. 143",
    status: "queued",
    progress: 0,
    phase: null,
    detail: null,
    sizeBytes: null,
  },
  {
    id: nextId(),
    series: seriesOrThrow("vanguard-protocol"),
    chapter: "Ch. 26",
    status: "paused",
    progress: 34,
    phase: null,
    detail: "14/38 pages",
    sizeBytes: null,
  },
  {
    id: nextId(),
    series: seriesOrThrow("wraith-of-the-nine-tails"),
    chapter: "Ch. 186",
    status: "done",
    progress: 100,
    phase: null,
    detail: null,
    sizeBytes: 18_874_368,
  },
  {
    id: nextId(),
    series: seriesOrThrow("tender-static"),
    chapter: "Ch. 13",
    status: "done",
    progress: 100,
    phase: null,
    detail: null,
    sizeBytes: 9_437_184,
  },
  {
    id: nextId(),
    series: seriesOrThrow("twelve-steps-to-ruin"),
    chapter: "Ch. 9",
    status: "failed",
    progress: 40,
    phase: null,
    detail: "MangaDex returned 503 while fetching page 9 — retry queued.",
    sizeBytes: null,
  },
];

export function nextDownloadId(): string {
  return nextId();
}
