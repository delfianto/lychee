// Read queries over the typed client, mapping API responses to the UI types in
// ../types. The API returns wider unions (plain strings) and ISO timestamps; the
// boundary cast + relativeTime bridge them so components stay strictly typed.

import type { RecentUpdate, Series } from "../types";
import { type Series as ApiSeries, api, type RecentUpdate as ApiUpdate } from "./client";
import { relativeTime } from "./format";

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
