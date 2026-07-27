// Providers (metadata/chapter sources) + trackers (progress-sync targets).
// Mirrors backend/src/integrations/seed.py: MangaDex is the only provider;
// AniList/MyAnimeList/MangaUpdates/NovelUpdates are the seeded trackers.

import type { components } from "../../api/schema";

type ProviderOut = components["schemas"]["ProviderOut"];
type TrackerOut = components["schemas"]["TrackerOut"];

export const providersDb: ProviderOut[] = [
  {
    id: "mangadex",
    name: "MangaDex",
    enabled: true,
    language: "en",
    autoMatch: true,
    fetchCovers: true,
    dataSaver: false,
    connected: true,
    accountName: "dwi.reader",
  },
];

export const trackersDb: TrackerOut[] = [
  {
    id: "anilist",
    name: "AniList",
    connected: true,
    syncOnRead: true,
    accountName: "dwireads",
    authKind: "oauth",
  },
  {
    id: "myanimelist",
    name: "MyAnimeList",
    connected: false,
    syncOnRead: false,
    accountName: null,
    authKind: "oauth",
  },
  {
    id: "mangaupdates",
    name: "MangaUpdates",
    connected: true,
    syncOnRead: false,
    accountName: "dwi_elfianto",
    authKind: "credentials",
  },
  {
    id: "novelupdates",
    name: "NovelUpdates",
    connected: false,
    syncOnRead: false,
    accountName: null,
    authKind: "unsupported",
  },
];
