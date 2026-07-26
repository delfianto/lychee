// Lightweight UI domain types (aligned with ../notes/decisions/). These will be
// superseded by the generated OpenAPI client (src/api/schema.d.ts) once the
// backend exposes the endpoints; for now they type the mock data.

export type ContentRating = "safe" | "suggestive" | "erotica" | "mature";
export type Demographic = "shonen" | "shojo" | "seinen" | "josei" | "none";
export type PublicationStatus = "ongoing" | "completed" | "hiatus" | "cancelled";

export type LibraryStatus =
  | "none"
  | "reading"
  | "on_hold"
  | "dropped"
  | "plan_to_read"
  | "completed"
  | "re_reading";

export type TagGroup = "genre" | "theme" | "content" | "format";

export interface Tag {
  id: string;
  name: string;
  group: TagGroup;
}

export interface Series {
  id: string;
  title: string;
  coverUrl: string;
  authors: string[];
  artists: string[];
  status: PublicationStatus;
  contentRating: ContentRating;
  demographic: Demographic;
  tags: Tag[];
  chapterCount: number;
  unreadCount: number;
  year?: number;
  description?: string;
  /** Per-user reading position, when in progress. */
  lastReadChapter?: number;
  totalChapters?: number;
  /** ISO 3166-1 alpha-2 (lowercase) origin country — drives the flag + manga/manhwa/manhua. */
  originCountry?: string;
  /** Community rating, 0–10. */
  rating?: number;
  /** This user's personal rating, 1–10. */
  userRating?: number;
  favorite?: boolean;
  kind?: "manga" | "comic" | "gallery";
  /** Number of media items, for gallery-kind series (stills / GIFs / MP4s). */
  imageCount?: number;
  /** Gallery-only metadata: the series the art depicts + depicted characters. */
  source?: string;
  characters?: string[];
  /** This user's shelf status (drives the library's status tabs). */
  libraryStatus?: LibraryStatus;
  /** Matched metadata provider slug (e.g. "mangadex"), or absent if unmatched. */
  provider?: string | null;
  /** Remote chapters not yet local, from the last sync (drives the "new" badge). */
  availableChapters?: number;
}

export interface RecentUpdate {
  series: Series;
  volume: number | null; // null = no volume (e.g. webtoons)
  chapter: string; // display value, e.g. "127" or "45.5"
  updatedAt: string; // relative label, e.g. "2h ago"
}

/** One gallery folder item — still, GIF, or progressive MP4. */
export type GalleryMediaKind = "image" | "gif" | "video";

export interface GalleryMediaItem {
  index: number;
  kind: GalleryMediaKind;
  /** Full-size still or progressive video stream (lightbox). */
  url: string;
  /** Small grid preview (~320px AVIF); lazy-built on first request if needed. */
  thumbUrl: string;
  posterUrl?: string | null;
}

/** Local readable chapter, or a remote-only row still waiting to download. */
export type ChapterStatus =
  | "downloaded"
  | "available"
  | "queued"
  | "downloading"
  | "paused"
  | "failed";

export interface Chapter {
  /** Local chapter id when downloaded; null for remote-only rows. */
  id: string | null;
  volume: number | null;
  number: string; // display value, e.g. "45" or "45.5"
  title?: string;
  group?: string; // scanlation / translation group
  language: string; // e.g. "en"
  uploadedAt: string; // relative label
  read: boolean;
  comments: number;
  status: ChapterStatus;
  providerChapterId?: string | null;
}

export interface VolumeGroup {
  volume: number | null; // null = no volume
  chapters: Chapter[];
}

export interface BrowseFilters {
  query: string;
  tags: Record<string, "include" | "exclude">;
  tagMode: "and" | "or";
  ratings: Set<ContentRating>;
  demographics: Set<Demographic>;
  statuses: Set<PublicationStatus>;
  readStates: Set<string>;
  sort: string;
}

/** A user-curated collection / reading list. */
export interface Collection {
  id: string;
  name: string;
  description?: string;
  seriesIds: string[];
}
