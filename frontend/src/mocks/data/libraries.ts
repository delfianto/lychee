// Library rows (the Libraries settings panel + Home's per-library storage tiles).

import type { components } from "../../api/schema";
import { daysAgo } from "../utils";
import { seriesCatalog } from "./series";

type LibraryOut = components["schemas"]["LibraryOut"];
type LibrarySummaryOut = components["schemas"]["LibrarySummaryOut"];

function countByKind(kind: string): number {
  return seriesCatalog.filter((s) => s.kind === kind).length;
}

export const librariesDb: LibraryOut[] = [
  {
    id: "lib-manga",
    name: "Manga",
    path: "/data/manga",
    kind: "manga",
    enabled: true,
    seriesCount: countByKind("manga"),
    lastScan: daysAgo(0),
  },
  {
    id: "lib-comics",
    name: "Comics",
    path: "/data/comics",
    kind: "comic",
    enabled: true,
    seriesCount: countByKind("comic"),
    lastScan: daysAgo(1),
  },
  {
    id: "lib-gallery",
    name: "Doujin & Gallery",
    path: "/data/gallery",
    kind: "gallery",
    enabled: true,
    seriesCount: countByKind("gallery"),
    lastScan: daysAgo(2),
  },
  {
    id: "lib-manga-archive",
    name: "Manga (Cold Storage)",
    path: "/mnt/archive/manga",
    kind: "manga",
    enabled: false,
    seriesCount: 0,
    lastScan: null,
  },
];

export const librarySummaryDb: LibrarySummaryOut[] = [
  { key: "lib-manga", title: "Manga", sizeGb: 84.6 },
  { key: "lib-comics", title: "Comics", sizeGb: 27.1 },
  { key: "lib-gallery", title: "Doujin & Gallery", sizeGb: 19.8 },
];
