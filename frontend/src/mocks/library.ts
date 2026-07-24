// Placeholder data so the UI renders before the API exists. Covers use picsum
// (dev only). Swap this module for the generated API client later.

import type {
  Chapter,
  Collection,
  ContentRating,
  Demographic,
  LibraryStatus,
  PublicationStatus,
  RecentUpdate,
  Series,
  Tag,
  TagGroup,
  VolumeGroup,
} from "../types";

// --- Tag registry ----------------------------------------------------------
const TAGS: Record<string, Tag> = {};
function t(id: string, name: string, group: TagGroup): Tag {
  const tag: Tag = { id, name, group };
  TAGS[id] = tag;
  return tag;
}

const GENRES: Tag[] = [
  t("action", "Action", "genre"),
  t("adventure", "Adventure", "genre"),
  t("comedy", "Comedy", "genre"),
  t("drama", "Drama", "genre"),
  t("fantasy", "Fantasy", "genre"),
  t("historical", "Historical", "genre"),
  t("horror", "Horror", "genre"),
  t("mystery", "Mystery", "genre"),
  t("romance", "Romance", "genre"),
  t("sci-fi", "Sci-Fi", "genre"),
  t("slice", "Slice of Life", "genre"),
  t("sports", "Sports", "genre"),
  t("thriller", "Thriller", "genre"),
  t("martial-arts", "Martial Arts", "genre"),
  t("superhero", "Superhero", "genre"),
  t("cooking", "Cooking", "genre"),
  t("art", "Art", "genre"),
  t("psychological", "Psychological", "genre"),
];
const THEMES: Tag[] = [
  t("isekai", "Isekai", "theme"),
  t("school", "School Life", "theme"),
  t("magic", "Magic", "theme"),
  t("military", "Military", "theme"),
  t("revenge", "Revenge", "theme"),
  t("survival", "Survival", "theme"),
  t("official", "Official", "theme"),
  t("fan-art", "Fan Art", "theme"),
  t("cosplay", "Cosplay", "theme"),
  t("illustration", "Illustration", "theme"),
];
const CONTENT: Tag[] = [
  t("gore", "Gore", "content"),
  t("sexual-violence", "Sexual Violence", "content"),
];

function cover(seed: string): string {
  return `https://picsum.photos/seed/${seed}/300/450`;
}

// --- Series seeds ----------------------------------------------------------
interface Seed {
  title: string;
  cc: string; // origin country (ISO alpha-2, lowercase)
  kind: NonNullable<Series["kind"]>;
  status: PublicationStatus;
  demographic: Demographic;
  rating: number;
  content: ContentRating;
  tags: string[];
  year: number;
  chapters: number;
  desc: string;
  fav?: boolean;
  unread?: number;
  lib?: LibraryStatus;
  read?: number; // last-read chapter (marks it in-progress)
  images?: number; // gallery image count (kind === "gallery")
  artists?: string[]; // gallery: illustrators / cosplayers / photographers
  characters?: string[]; // gallery: depicted characters
  source?: string; // gallery: source series
}

const SEEDS: Seed[] = [
  { title: "Dungeon Meshi", cc: "jp", kind: "manga", status: "completed", demographic: "seinen", rating: 9.2, content: "safe", tags: ["fantasy", "comedy", "adventure", "cooking"], year: 2014, chapters: 102, fav: true, unread: 12, lib: "reading", read: 45, desc: "When young adventurer Laios and his party are wiped out by a dragon deep in a labyrinth, they resolve to march right back down — and this time, live off the monsters they slay along the way." },
  { title: "Frieren: Beyond Journey's End", cc: "jp", kind: "manga", status: "ongoing", demographic: "shonen", rating: 9.6, content: "safe", tags: ["fantasy", "adventure", "drama"], year: 2020, chapters: 127, fav: true, unread: 3, lib: "reading", read: 120, desc: "The elf mage Frieren outlived the party she once saved the world with. Now she sets out to truly understand the humans whose brief lives left such a mark on her own." },
  { title: "Berserk", cc: "jp", kind: "manga", status: "hiatus", demographic: "seinen", rating: 9.8, content: "mature", tags: ["action", "fantasy", "horror"], year: 1989, chapters: 375, fav: true, lib: "on_hold", desc: "Guts, the Black Swordsman, seeks vengeance against the demonic forces that branded him — a brutal dark-fantasy epic of ambition, friendship and fate." },
  { title: "Vinland Saga", cc: "jp", kind: "manga", status: "ongoing", demographic: "seinen", rating: 9.1, content: "mature", tags: ["action", "adventure", "historical"], year: 2005, chapters: 210, unread: 7, lib: "reading", read: 190, desc: "A young Viking bent on revenge is slowly forced to reckon with what a life beyond endless war might look like." },
  { title: "One Piece", cc: "jp", kind: "manga", status: "ongoing", demographic: "shonen", rating: 9.3, content: "safe", tags: ["action", "adventure", "fantasy"], year: 1997, chapters: 1102, lib: "plan_to_read", desc: "Monkey D. Luffy sets sail with a crew of misfits in search of the legendary treasure that will crown him King of the Pirates." },
  { title: "Vagabond", cc: "jp", kind: "manga", status: "hiatus", demographic: "seinen", rating: 9.4, content: "mature", tags: ["action", "historical", "martial-arts"], year: 1998, chapters: 327, desc: "A fictionalized retelling of the life of Japan's greatest swordsman, Miyamoto Musashi, and his relentless pursuit of what it means to be strong." },
  { title: "20th Century Boys", cc: "jp", kind: "manga", status: "completed", demographic: "seinen", rating: 8.9, content: "safe", tags: ["mystery", "sci-fi", "thriller"], year: 1999, chapters: 249, lib: "completed", desc: "A childhood prophecy scrawled in a secret hideout begins to come true decades later, dragging a group of former friends into a plot to end the world." },
  { title: "Goodnight Punpun", cc: "jp", kind: "manga", status: "completed", demographic: "seinen", rating: 9.0, content: "mature", tags: ["drama", "slice", "psychological"], year: 2007, chapters: 147, lib: "completed", desc: "An unflinching coming-of-age story that follows an ordinary boy — drawn as a tiny bird — through the quiet devastations of growing up." },
  { title: "Chainsaw Man", cc: "jp", kind: "manga", status: "ongoing", demographic: "shonen", rating: 8.7, content: "mature", tags: ["action", "horror", "comedy"], year: 2018, chapters: 150, fav: true, unread: 5, lib: "reading", read: 97, desc: "Denji fuses with his chainsaw-devil dog to become a devil hunter for a shadowy agency, chasing a dream as simple as a full stomach and a normal life." },
  { title: "Blue Period", cc: "jp", kind: "manga", status: "ongoing", demographic: "seinen", rating: 8.4, content: "safe", tags: ["drama", "art", "slice"], year: 2017, chapters: 60, lib: "dropped", desc: "A high-achieving but aimless student discovers painting and throws himself at the brutal, exhilarating world of art school entrance exams." },
  { title: "Witch Hat Atelier", cc: "jp", kind: "manga", status: "ongoing", demographic: "shonen", rating: 8.6, content: "safe", tags: ["fantasy", "adventure", "magic"], year: 2016, chapters: 75, desc: "In a world where magic is a secret drawn with pen and ink, a curious girl is taken in by a mysterious witch and begins to learn the craft." },
  { title: "Monster", cc: "jp", kind: "manga", status: "completed", demographic: "seinen", rating: 9.1, content: "mature", tags: ["mystery", "thriller", "psychological"], year: 1994, chapters: 162, lib: "completed", desc: "A gifted surgeon saves the life of a boy who grows into a monster, and must hunt his own act of mercy across a haunted post–Cold War Europe." },
  { title: "Akira", cc: "jp", kind: "manga", status: "completed", demographic: "seinen", rating: 8.8, content: "mature", tags: ["sci-fi", "action"], year: 1982, chapters: 120, lib: "re_reading", read: 30, desc: "In Neo-Tokyo, a biker gang member's latent psychic power spirals out of control, threatening to unleash the same catastrophe that once leveled the city." },
  { title: "Solo Leveling", cc: "kr", kind: "manga", status: "completed", demographic: "none", rating: 8.5, content: "suggestive", tags: ["action", "fantasy"], year: 2018, chapters: 179, fav: true, lib: "completed", desc: "The world's weakest hunter gains a mysterious system that lets him level up without limit, rising from bottom-rung fodder toward monstrous power." },
  { title: "Tower of God", cc: "kr", kind: "manga", status: "ongoing", demographic: "none", rating: 8.2, content: "suggestive", tags: ["fantasy", "adventure", "action"], year: 2010, chapters: 600, unread: 1, lib: "reading", read: 540, desc: "A boy enters a mysterious tower to chase the only person who ever mattered to him, climbing floor by deadly floor toward whatever waits at the top." },
  { title: "Omniscient Reader's Viewpoint", cc: "kr", kind: "manga", status: "ongoing", demographic: "none", rating: 8.9, content: "suggestive", tags: ["action", "fantasy", "drama"], year: 2020, chapters: 220, lib: "plan_to_read", desc: "The only reader who finished a long-dead web novel wakes to find its apocalypse coming true — and he alone knows how the story is supposed to go." },
  { title: "The Ravages of Time", cc: "cn", kind: "manga", status: "ongoing", demographic: "none", rating: 8.3, content: "safe", tags: ["historical", "action", "military"], year: 2001, chapters: 600, desc: "A cold retelling of the Three Kingdoms era from the shadows, where a secret band of strategists moves warlords like pieces across a bleeding board." },
  { title: "Saga", cc: "us", kind: "comic", status: "ongoing", demographic: "none", rating: 9.0, content: "mature", tags: ["sci-fi", "fantasy", "romance"], year: 2012, chapters: 66, fav: true, unread: 2, lib: "reading", read: 54, desc: "Two soldiers from opposite sides of a galactic war fall in love and flee with their newborn daughter, hunted across a strange and gorgeous universe." },
  { title: "Watchmen", cc: "us", kind: "comic", status: "completed", demographic: "none", rating: 9.2, content: "mature", tags: ["superhero", "mystery", "drama"], year: 1986, chapters: 12, fav: true, lib: "completed", desc: "In an alternate 1985, the murder of a costumed vigilante pulls a group of retired heroes into a conspiracy that questions the very idea of heroism." },
  { title: "The Sandman", cc: "us", kind: "comic", status: "completed", demographic: "none", rating: 9.1, content: "mature", tags: ["fantasy", "horror", "drama"], year: 1989, chapters: 75, fav: true, desc: "Freed after decades of captivity, Dream of the Endless sets out to rebuild his realm — a sprawling myth woven from history, folklore and nightmare." },

  // --- Galleries (image sets: official art, fan art, cosplay) ---
  { title: "Frieren — Official Illustrations", cc: "jp", kind: "gallery", status: "completed", demographic: "none", rating: 9.4, content: "safe", tags: ["fantasy", "art", "official", "illustration"], year: 2023, chapters: 0, images: 36, fav: true, artists: ["Tsukasa Abe"], characters: ["Frieren", "Fern", "Stark"], source: "Frieren: Beyond Journey's End", desc: "Official character art and promotional illustrations from the manga and anime." },
  { title: "Chainsaw Man — Fan Art", cc: "jp", kind: "gallery", status: "completed", demographic: "none", rating: 8.9, content: "suggestive", tags: ["action", "fan-art", "art"], year: 2022, chapters: 0, images: 52, artists: ["Various Artists"], characters: ["Denji", "Power", "Makima"], source: "Chainsaw Man", desc: "A community collection of fan illustrations of Denji, Power, Makima and the rest." },
  { title: "Marin Kitagawa — Cosplay", cc: "jp", kind: "gallery", status: "completed", demographic: "none", rating: 8.6, content: "suggestive", tags: ["cosplay", "romance"], year: 2023, chapters: 0, images: 28, artists: ["Enako", "Shirogane Sama"], characters: ["Marin Kitagawa"], source: "My Dress-Up Darling", desc: "Cosplay photosets of My Dress-Up Darling's Marin, from various artists and events." },
  { title: "Genshin Impact — Splash Art", cc: "cn", kind: "gallery", status: "completed", demographic: "none", rating: 9.0, content: "safe", tags: ["fantasy", "official", "art", "illustration"], year: 2020, chapters: 0, images: 44, fav: true, artists: ["HoYoverse"], characters: ["Raiden Shogun", "Zhongli", "Nahida"], source: "Genshin Impact", desc: "Character splash screens and key art from across the regions of Teyvat." },
  { title: "Berserk — Miura Artworks", cc: "jp", kind: "gallery", status: "completed", demographic: "none", rating: 9.7, content: "mature", tags: ["fantasy", "art", "official"], year: 2019, chapters: 0, images: 60, artists: ["Kentaro Miura"], characters: ["Guts", "Griffith"], source: "Berserk", desc: "High-resolution scans of Kentaro Miura's cover paintings and colour spreads." },
  { title: "Studio Ghibli — Background Art", cc: "jp", kind: "gallery", status: "completed", demographic: "none", rating: 9.2, content: "safe", tags: ["art", "official", "illustration"], year: 2021, chapters: 0, images: 40, artists: ["Kazuo Oga"], characters: [], source: "Studio Ghibli", desc: "Hand-painted background layouts and concept art across the studio's films." },
];

let n = 0;
function fromSeed(s: Seed): Series {
  n += 1;
  const id = `s${n}`;
  return {
    id,
    title: s.title,
    coverUrl: cover(id),
    authors: ["Author Name"],
    artists: s.artists ?? ["Artist Name"],
    status: s.status,
    contentRating: s.content,
    demographic: s.demographic,
    tags: s.tags.map((tid) => TAGS[tid]).filter((x): x is Tag => Boolean(x)),
    chapterCount: s.chapters,
    unreadCount: s.unread ?? 0,
    year: s.year,
    description: s.desc,
    originCountry: s.cc,
    rating: s.rating,
    favorite: s.fav ?? false,
    kind: s.kind,
    imageCount: s.images,
    source: s.source,
    characters: s.characters,
    libraryStatus: s.lib ?? "none",
    ...(s.read !== undefined ? { lastReadChapter: s.read, totalChapters: s.chapters } : {}),
  };
}

export const librarySeries: Series[] = SEEDS.map(fromSeed);

export const continueReading: Series[] = librarySeries
  .filter((s) => s.lastReadChapter !== undefined)
  .slice(0, 6);

// Chapter-based content only — galleries have images, not chapter updates.
const chaptered = librarySeries.filter((s) => s.kind !== "gallery");
export const recentUpdates: RecentUpdate[] = Array.from({ length: 24 }, (_, i) => {
  const series = chaptered[i % chaptered.length];
  const chapNum = series.chapterCount - (i % 5);
  return {
    series,
    volume: i % 4 === 3 ? null : Math.max(1, Math.round(chapNum / 10)),
    chapter: String(chapNum),
    updatedAt: i < 12 ? `${i + 1}h ago` : `${i - 11}d ago`,
  };
});

/** Every unread chapter across the library (newest first per series) — for the
    "Unread chapters" feed. Total matches the Home "Unread chapters" stat. */
export const unreadChapters: RecentUpdate[] = librarySeries
  .filter((s) => s.unreadCount > 0)
  .flatMap((s) =>
    Array.from({ length: s.unreadCount }, (_, k) => {
      const chapNum = s.chapterCount - k;
      return {
        series: s,
        volume: Math.max(1, Math.round(chapNum / 10)),
        chapter: String(chapNum),
        updatedAt: `${k + 1}d ago`,
      };
    }),
  );

/** Newest series first (reverse of insertion order) — for the Home "Recently added" rail. */
export const recentlyAdded: Series[] = [...librarySeries].reverse();

/** Seed collections; the store persists user edits over these in localStorage. */
export const initialCollections: Collection[] = [
  { id: "l1", name: "Currently reading", seriesIds: ["s1", "s2", "s4", "s9", "s15"] },
  { id: "l2", name: "All-time favorites", seriesIds: ["s3", "s2", "s14", "s18"] },
  { id: "l3", name: "To re-read", seriesIds: ["s13", "s6", "s12"] },
  { id: "l4", name: "Seinen essentials", seriesIds: ["s3", "s6", "s7", "s8", "s12"] },
];

export function findSeries(id: string): Series {
  return librarySeries.find((s) => s.id === id) ?? librarySeries[0];
}

export function randomSeriesId(): string {
  const i = Math.floor(Math.random() * librarySeries.length);
  return librarySeries[i].id;
}

/** A named library slice, resolved from a route key (manga / comics / books / …). */
export interface LibraryDef {
  key: string;
  title: string;
  series: Series[];
}

export function libraryFor(key: string): LibraryDef {
  switch (key) {
    case "favorites":
      return { key, title: "Favorites", series: librarySeries.filter((s) => s.favorite) };
    case "reading":
      // The reading shelf — manga + comics currently in "reading" status.
      return { key, title: "Reading", series: librarySeries.filter((s) => s.libraryStatus === "reading") };
    case "comics":
      return { key, title: "Comics", series: librarySeries.filter((s) => s.kind === "comic") };
    case "gallery":
      return { key, title: "Gallery", series: librarySeries.filter((s) => s.kind === "gallery") };
    default:
      return { key: "manga", title: "Manga", series: librarySeries.filter((s) => s.kind === "manga") };
  }
}

// --- Per-library storage (mock) --------------------------------------------
/** Storage used per library, shown on the Home dashboard. Zero-size libraries
    are hidden there so empty ones don't clutter the strip. */
export interface LibrarySummary {
  key: string; // route key → /manga, /comics
  title: string;
  sizeGb: number;
}
export const librarySummaries: LibrarySummary[] = [
  { key: "manga", title: "Manga", sizeGb: 18.6 },
  { key: "comics", title: "Comics", sizeGb: 4.3 },
  { key: "gallery", title: "Gallery", sizeGb: 9.7 },
];

/** Placeholder images for a gallery's detail grid + lightbox (kind === "gallery"). */
export function galleryImages(id: string, count = 24): string[] {
  return Array.from({ length: count }, (_, i) => `https://picsum.photos/seed/${id}-g${i}/800/1000`);
}

// --- Chapters (series detail) ----------------------------------------------
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

export const browseTagGroups: { group: string; tags: Tag[] }[] = [
  { group: "Genre", tags: GENRES },
  { group: "Theme", tags: THEMES },
  { group: "Content", tags: CONTENT },
];

export const allBrowseTags: Tag[] = browseTagGroups.flatMap((g) => g.tags);
