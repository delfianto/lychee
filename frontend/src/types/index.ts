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
}

export interface RecentUpdate {
  series: Series;
  chapterLabel: string; // e.g. "Ch. 120"
  updatedAt: string; // relative label, e.g. "2h ago"
}

export interface Chapter {
  id: string;
  volume: number | null;
  number: string; // display value, e.g. "45" or "45.5"
  title?: string;
  group?: string; // scanlation / translation group
  language: string; // e.g. "en"
  uploadedAt: string; // relative label
  read: boolean;
  comments: number;
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
