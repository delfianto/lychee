// About/import/sync/filesystem-browser fixtures — the smaller settings panels
// that don't need a whole file to themselves.

import type { components } from "../../api/schema";
import { hoursAgo } from "../utils";

type AboutOut = components["schemas"]["AboutOut"];
type ImportConfigOut = components["schemas"]["ImportConfigOut"];
type SyncOut = components["schemas"]["SyncOut"];
type FsEntry = components["schemas"]["FsEntry"];

const SERVER_STARTED = Date.now() - 3 * 86_400_000 - 4 * 3_600_000;

export function buildAbout(): AboutOut {
  return {
    version: "0.1.0-beta.1",
    platform: "linux-x86_64 · Python 3.14.0",
    database: "SQLite 3.46 · 214.7 MB",
    started: new Date(SERVER_STARTED).toISOString(),
    uptimeSeconds: Math.floor((Date.now() - SERVER_STARTED) / 1000),
  };
}

export const importConfig: ImportConfigOut = {
  enabled: true,
  quality: 75,
  filenamePattern: "{title} - c{chapter} ({group})",
  patternPresets: [
    { name: "Standard", pattern: "{title} - c{chapter} ({group})" },
    { name: "Volume-based", pattern: "{title} v{volume} - c{chapter}" },
    { name: "Group-first", pattern: "[{group}] {title} - c{chapter}" },
  ],
};

export const syncState: SyncOut = {
  lastSync: hoursAgo(6),
  autoEveryMinutes: 60,
  newChapters: 14,
  syncing: false,
  paused: false,
  parallelSyncs: 2,
  jobs: [
    {
      id: "sync-job-1",
      kind: "sync",
      title: "Nightfall Requiem",
      source: "MangaDex",
      status: "running",
      progress: 65,
      detail: "Pulling chapters for Nightfall Requiem from MangaDex (13/20)",
      error: null,
    },
    {
      id: "sync-job-2",
      kind: "scan",
      title: "Wraith of the Nine Tails",
      source: "/data/manga",
      status: "queued",
      progress: 0,
      detail: "Queued for indexing in /data/manga",
      error: null,
    },
    {
      id: "sync-job-3",
      kind: "scan",
      title: "Corrupt Vol.04.cbz",
      source: "/data/manga/Bloodmoon Apothecary",
      status: "failed",
      progress: 0,
      detail: "Unreadable file while indexing Corrupt Vol.04.cbz",
      error: "Archive is not a valid ZIP/CBZ container",
    },
    {
      id: "sync-job-4",
      kind: "import",
      title: "MangaDex Account",
      source: "MangaDex",
      status: "done",
      progress: 100,
      detail: "Synced 18 manga from MangaDex",
      error: null,
    },
  ],
};

// --- filesystem browser (AddLibraryModal / ImportPanel path picker) --------

const FS_ROOT = "/data";
export const fsTree = new Map<string, FsEntry[]>([
  [
    FS_ROOT,
    [
      { name: "manga", path: "/data/manga", kind: "dir" },
      { name: "comics", path: "/data/comics", kind: "dir" },
      { name: "gallery", path: "/data/gallery", kind: "dir" },
      { name: "incoming", path: "/data/incoming", kind: "dir" },
      { name: "downloads", path: "/data/downloads", kind: "dir" },
    ],
  ],
  [
    "/data/manga",
    [
      { name: "Nightfall Requiem", path: "/data/manga/Nightfall Requiem", kind: "dir" },
      {
        name: "Wraith of the Nine Tails",
        path: "/data/manga/Wraith of the Nine Tails",
        kind: "dir",
      },
      { name: "Bloodmoon Apothecary", path: "/data/manga/Bloodmoon Apothecary", kind: "dir" },
    ],
  ],
  [
    "/data/comics",
    [{ name: "Vanguard Protocol", path: "/data/comics/Vanguard Protocol", kind: "dir" }],
  ],
  [
    "/data/gallery",
    [{ name: "Starlit Chronicles", path: "/data/gallery/Starlit Chronicles", kind: "dir" }],
  ],
  [
    "/data/incoming",
    [
      { name: "new-chapter-batch.zip", path: "/data/incoming/new-chapter-batch.zip", kind: "file" },
      { name: "unsorted", path: "/data/incoming/unsorted", kind: "dir" },
    ],
  ],
  ["/data/incoming/unsorted", []],
  ["/data/downloads", []],
  ["/data/manga/Nightfall Requiem", []],
  ["/data/manga/Wraith of the Nine Tails", []],
  ["/data/manga/Bloodmoon Apothecary", []],
  ["/data/comics/Vanguard Protocol", []],
  ["/data/gallery/Starlit Chronicles", []],
]);

export function fsParentOf(path: string): string | null {
  if (path === FS_ROOT) return null;
  const idx = path.lastIndexOf("/");
  return idx <= 0 ? FS_ROOT : path.slice(0, idx);
}

export function fsRoot(): string {
  return FS_ROOT;
}

export function fsMkdir(parent: string, name: string): FsEntry {
  const path = `${parent === "/" ? "" : parent}/${name}`;
  const entry: FsEntry = { name, path, kind: "dir" };
  const siblings = fsTree.get(parent) ?? [];
  siblings.push(entry);
  fsTree.set(parent, siblings);
  fsTree.set(path, []);
  return entry;
}
