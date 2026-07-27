// The series catalog: a handful of hand-authored "flagship" entries (rich
// descriptions, deliberately varied states) plus a procedurally generated
// long tail so grids/pagination/filtering/search have a realistic amount of
// material to work with. Every title here is invented — no real manga/comic
// franchises — generated purely to give the library a plausible *shape*.

import type { components } from "../../api/schema";
import { chance, daysAgo, pick, pickN, randInt, rngFor, weighted } from "../utils";
import {
  CONTENT_IDS,
  CONTENT_RATINGS,
  DEMOGRAPHICS,
  FORMAT_IDS,
  GENRE_IDS,
  tag,
  THEME_IDS,
} from "./taxonomy";
import {
  creatorName,
  GALLERY_CHARACTERS,
  GALLERY_FRANCHISES,
  generateComicTitle,
  generateGalleryTitle,
  generateMangaTitle,
} from "./names";

type SeriesOut = components["schemas"]["SeriesOut"];

type Kind = "manga" | "comic" | "gallery";
type Status = "ongoing" | "completed" | "hiatus" | "cancelled";
type ContentRating = (typeof CONTENT_RATINGS)[number];
type Demographic = (typeof DEMOGRAPHICS)[number] | "none";
type LibraryStatus = "none" | "reading" | "on_hold" | "dropped" | "plan_to_read" | "completed" | "re_reading";

export interface SeriesSeed {
  id: string;
  kind: Kind;
  title: string;
  authors: string[];
  artists: string[];
  status: Status;
  contentRating: ContentRating;
  demographic: Demographic;
  tagIds: string[];
  year: number;
  description: string;
  originCountry: string;
  provider: string | null;
  favorite: boolean;
  libraryStatus: LibraryStatus;
  communityRating: number | null;
  userRating: number | null;
  chapterCount: number;
  availableChapters: number;
  unreadCount: number;
  lastReadChapter: number | null;
  totalChapters: number | null;
  imageCount?: number;
  source?: string;
  characters?: string[];
}

function toSeriesOut(seed: SeriesSeed): SeriesOut {
  const rng = rngFor(seed.id);
  return {
    id: seed.id,
    title: seed.title,
    coverUrl: `/api/series/${seed.id}/cover`,
    authors: seed.authors,
    artists: seed.artists,
    status: seed.status,
    contentRating: seed.contentRating,
    demographic: seed.demographic,
    tags: seed.tagIds.map(tag),
    chapterCount: seed.chapterCount,
    unreadCount: seed.unreadCount,
    year: seed.year,
    description: seed.description,
    lastReadChapter: seed.lastReadChapter,
    totalChapters: seed.totalChapters,
    originCountry: seed.originCountry,
    rating: seed.communityRating,
    userRating: seed.userRating,
    favorite: seed.favorite,
    kind: seed.kind,
    imageCount: seed.imageCount ?? null,
    source: seed.source ?? null,
    characters: seed.characters ?? null,
    libraryStatus: seed.libraryStatus,
    provider: seed.provider,
    availableChapters: seed.availableChapters,
    chaptersSyncedAt: seed.provider ? daysAgo(randInt(rng, 0, 9)) : null,
  };
}

// --- hand-authored flagships ------------------------------------------------

const FLAGSHIPS: SeriesSeed[] = [
  {
    id: "nightfall-requiem",
    kind: "manga",
    title: "Nightfall Requiem",
    authors: ["Hiroshi Kurosawa"],
    artists: ["Hiroshi Kurosawa"],
    status: "ongoing",
    contentRating: "suggestive",
    demographic: "shonen",
    tagIds: ["genre-action", "genre-fantasy", "theme-supernatural", "theme-demons"],
    year: 2021,
    description:
      "A cursed swordsman wakes with no memory beyond the name carved into his blade, hunted by a cult that worships the night itself. Each chapter peels back another layer of the empire's buried war between light-bound knights and the things that live in eclipse.",
    originCountry: "jp",
    provider: "mangadex",
    favorite: true,
    libraryStatus: "reading",
    communityRating: 8.7,
    userRating: 9,
    chapterCount: 142,
    availableChapters: 3,
    unreadCount: 6,
    lastReadChapter: 136,
    totalChapters: null,
  },
  {
    id: "cartographers-daughter",
    kind: "manga",
    title: "The Cartographer's Daughter",
    authors: ["Nanami Endo"],
    artists: ["Nanami Endo"],
    status: "completed",
    contentRating: "safe",
    demographic: "seinen",
    tagIds: ["genre-mystery", "genre-drama", "genre-historical"],
    year: 2016,
    description:
      "In a city redrawn every decade by an unseen hand, a mapmaker's daughter inherits the family trade — and the impossible job of charting streets that refuse to stay put. A quiet, melancholy mystery about memory, cartography, and the people a city forgets.",
    originCountry: "jp",
    provider: "mangadex",
    favorite: false,
    libraryStatus: "completed",
    communityRating: 9.1,
    userRating: 10,
    chapterCount: 58,
    availableChapters: 0,
    unreadCount: 0,
    lastReadChapter: 58,
    totalChapters: 58,
  },
  {
    id: "glass-menagerie-high",
    kind: "manga",
    title: "Glass Menagerie High",
    authors: ["Yui Matsumoto"],
    artists: ["Riko Fujii"],
    status: "ongoing",
    contentRating: "safe",
    demographic: "shojo",
    tagIds: ["genre-romance", "theme-school-life", "genre-comedy"],
    year: 2023,
    description:
      "Transferring mid-year to the country's strictest all-glass-walled academy, Emi Aihara discovers everyone can see everything — except what's actually going on in her upperclassman's head. A slow-burn romance told almost entirely through things left unsaid.",
    originCountry: "jp",
    provider: "mangadex",
    favorite: false,
    libraryStatus: "reading",
    communityRating: 7.9,
    userRating: 8,
    chapterCount: 31,
    availableChapters: 1,
    unreadCount: 4,
    lastReadChapter: 27,
    totalChapters: null,
  },
  {
    id: "iron-bloom",
    kind: "manga",
    title: "Iron Bloom",
    authors: ["Sakura Hoshino"],
    artists: ["Sakura Hoshino"],
    status: "ongoing",
    contentRating: "safe",
    demographic: "josei",
    tagIds: ["genre-drama", "genre-slice-of-life"],
    year: 2022,
    description:
      "A single mother reopens her late husband's ironworks in a town that would rather see it close, one difficult apprentice and one skeptical customer at a time.",
    originCountry: "jp",
    provider: null,
    favorite: false,
    libraryStatus: "plan_to_read",
    communityRating: 7.4,
    userRating: null,
    chapterCount: 19,
    availableChapters: 0,
    unreadCount: 19,
    lastReadChapter: null,
    totalChapters: null,
  },
  {
    id: "wraith-of-the-nine-tails",
    kind: "manga",
    title: "Wraith of the Nine Tails",
    authors: ["Takeshi Okada"],
    artists: ["Daichi Kishida"],
    status: "ongoing",
    contentRating: "suggestive",
    demographic: "shonen",
    tagIds: ["genre-isekai", "genre-fantasy", "genre-comedy", "theme-reincarnation"],
    year: 2020,
    description:
      "Reincarnated as the weakest fox spirit in a mountain full of ancient youkai, Tobei has exactly one power: everyone underestimates him. A loud, funny, occasionally very sincere power-fantasy about being counted out.",
    originCountry: "jp",
    provider: "mangadex",
    favorite: true,
    libraryStatus: "reading",
    communityRating: 8.2,
    userRating: 8,
    chapterCount: 187,
    availableChapters: 5,
    unreadCount: 12,
    lastReadChapter: 175,
    totalChapters: null,
  },
  {
    id: "requiem-for-the-vanished-king",
    kind: "manga",
    title: "Requiem for the Vanished King",
    authors: ["Kenji Arakawa"],
    artists: ["Kenji Arakawa"],
    status: "hiatus",
    contentRating: "suggestive",
    demographic: "seinen",
    tagIds: ["genre-historical", "genre-wuxia", "genre-drama"],
    year: 2017,
    description:
      "Twelve sword schools, one murdered emperor, and a wandering blade-for-hire who insists he's retired. On hiatus since the mangaka's injury; fans are still arguing about who the ending is going to break.",
    originCountry: "jp",
    provider: "mangadex",
    favorite: false,
    libraryStatus: "on_hold",
    communityRating: 8.9,
    userRating: 9,
    chapterCount: 76,
    availableChapters: 0,
    unreadCount: 2,
    lastReadChapter: 74,
    totalChapters: null,
  },
  {
    id: "static-hearts",
    kind: "manga",
    title: "Static Hearts",
    authors: ["Ren Watanabe"],
    artists: ["Ren Watanabe"],
    status: "completed",
    contentRating: "safe",
    demographic: "shonen",
    tagIds: ["genre-boys-love", "genre-romance", "theme-school-life"],
    year: 2019,
    description:
      "Two rival radio-club members are assigned to co-host the same late-night broadcast slot, and neither one can figure out why the silence between songs feels louder every week.",
    originCountry: "jp",
    provider: "mangadex",
    favorite: false,
    libraryStatus: "completed",
    communityRating: 8.4,
    userRating: 8,
    chapterCount: 24,
    availableChapters: 0,
    unreadCount: 0,
    lastReadChapter: 24,
    totalChapters: 24,
  },
  {
    id: "tender-static",
    kind: "manga",
    title: "Tender Static",
    authors: ["Mei Inoue"],
    artists: ["Aiko Tanaka"],
    status: "ongoing",
    contentRating: "safe",
    demographic: "josei",
    tagIds: ["genre-girls-love", "genre-slice-of-life", "theme-music"],
    year: 2023,
    description:
      "A retired idol and the sound engineer who never got to see her perform live open a tiny record shop together, and slowly relearn what music sounds like when nobody's watching.",
    originCountry: "jp",
    provider: "mangadex",
    favorite: true,
    libraryStatus: "reading",
    communityRating: 8.6,
    userRating: 9,
    chapterCount: 14,
    availableChapters: 1,
    unreadCount: 2,
    lastReadChapter: 12,
    totalChapters: null,
  },
  {
    id: "mecha-vandal-zero",
    kind: "manga",
    title: "Mecha Vandal Zero",
    authors: ["Souta Kobayashi"],
    artists: ["Souta Kobayashi"],
    status: "ongoing",
    contentRating: "suggestive",
    demographic: "shonen",
    tagIds: ["genre-mecha", "genre-sci-fi", "theme-military"],
    year: 2022,
    description:
      "Salvaged war machines, a scrapyard crew of teenage pilots, and a corporate arms dealer who'd very much like their illegal mech back. Loud, fast, unapologetically about giant robots hitting each other.",
    originCountry: "jp",
    provider: "mangadex",
    favorite: false,
    libraryStatus: "reading",
    communityRating: 7.6,
    userRating: 7,
    chapterCount: 46,
    availableChapters: 2,
    unreadCount: 3,
    lastReadChapter: 43,
    totalChapters: null,
  },
  {
    id: "court-of-hollow-petals",
    kind: "manga",
    title: "Court of Hollow Petals",
    authors: ["Emi Sato"],
    artists: ["Emi Sato"],
    status: "completed",
    contentRating: "mature",
    demographic: "josei",
    tagIds: ["genre-psychological", "genre-romance", "genre-tragedy"],
    year: 2015,
    description:
      "A concubine plays a decade-long game of patience inside a court designed to erase her, one perfectly arranged flower at a time.",
    originCountry: "jp",
    provider: "mangadex",
    favorite: false,
    libraryStatus: "completed",
    communityRating: 9.3,
    userRating: 10,
    chapterCount: 89,
    availableChapters: 0,
    unreadCount: 0,
    lastReadChapter: 89,
    totalChapters: 89,
  },
  {
    id: "twelve-steps-to-ruin",
    kind: "manga",
    title: "Twelve Steps to Ruin",
    authors: ["Akira Nakamura"],
    artists: ["Yuki Ito"],
    status: "ongoing",
    contentRating: "suggestive",
    demographic: "seinen",
    tagIds: ["genre-crime", "genre-thriller", "genre-psychological"],
    year: 2024,
    description:
      "A disgraced detective takes a job protecting the man she's certain framed her — and has exactly twelve days to prove it before the statute of limitations runs out on everyone involved.",
    originCountry: "jp",
    provider: "mangadex",
    favorite: false,
    libraryStatus: "reading",
    communityRating: 8.1,
    userRating: null,
    chapterCount: 9,
    availableChapters: 1,
    unreadCount: 1,
    lastReadChapter: 8,
    totalChapters: null,
  },
  {
    id: "last-cicada-summer",
    kind: "manga",
    title: "The Last Cicada Summer",
    authors: ["Haruto Yamamoto"],
    artists: ["Haruto Yamamoto"],
    status: "completed",
    contentRating: "safe",
    demographic: "shonen",
    tagIds: ["genre-sports", "genre-slice-of-life"],
    year: 2014,
    description:
      "A third-string pitcher gets one final summer tournament to matter, on a team that's already decided to disband afterward. Quietly one of the most re-read completed sports series in the library.",
    originCountry: "jp",
    provider: "mangadex",
    favorite: true,
    libraryStatus: "re_reading",
    communityRating: 9.0,
    userRating: 10,
    chapterCount: 42,
    availableChapters: 0,
    unreadCount: 0,
    lastReadChapter: 30,
    totalChapters: 42,
  },
  {
    id: "bloodmoon-apothecary",
    kind: "manga",
    title: "Bloodmoon Apothecary",
    authors: ["Ha-eun Park"],
    artists: ["Seo-yeon Kang"],
    status: "ongoing",
    contentRating: "suggestive",
    demographic: "shonen",
    tagIds: ["genre-horror", "theme-supernatural", "genre-medical"],
    year: 2023,
    description:
      "A night-shift pharmacist discovers her new clinic sits on a ley line that only the dead can find, and now she's the only doctor in town who'll treat them.",
    originCountry: "kr",
    provider: "mangadex",
    favorite: false,
    libraryStatus: "reading",
    communityRating: 8.3,
    userRating: 8,
    chapterCount: 63,
    availableChapters: 4,
    unreadCount: 8,
    lastReadChapter: 55,
    totalChapters: null,
  },
  {
    id: "silverleaf-testament",
    kind: "manga",
    title: "Silverleaf Testament",
    authors: ["Takeshi Okada"],
    artists: ["Takeshi Okada"],
    status: "cancelled",
    contentRating: "safe",
    demographic: "seinen",
    tagIds: ["genre-philosophical", "genre-drama"],
    year: 2018,
    description:
      "An aging philosopher's final lecture series, told backwards from his last day to his first — cancelled after volume four when the author's health made finishing impossible; still worth the read.",
    originCountry: "jp",
    provider: null,
    favorite: false,
    libraryStatus: "dropped",
    communityRating: 7.8,
    userRating: 6,
    chapterCount: 31,
    availableChapters: 0,
    unreadCount: 0,
    lastReadChapter: 20,
    totalChapters: 31,
  },
  // --- comics ---
  {
    id: "vanguard-protocol",
    kind: "comic",
    title: "Vanguard Protocol",
    authors: ["Morgan Sterling"],
    artists: ["Casey Blackwood"],
    status: "ongoing",
    contentRating: "suggestive",
    demographic: "none",
    tagIds: ["genre-superhero", "genre-sci-fi"],
    year: 2021,
    description:
      "A decommissioned government super-team gets reactivated for one mission that keeps not ending. Sharp, talky, more about the paperwork of heroism than the punching — though there's plenty of that too.",
    originCountry: "us",
    provider: null,
    favorite: true,
    libraryStatus: "reading",
    communityRating: 8.0,
    userRating: 9,
    chapterCount: 27,
    availableChapters: 1,
    unreadCount: 3,
    lastReadChapter: 24,
    totalChapters: null,
  },
  {
    id: "precinct-9-blackout",
    kind: "comic",
    title: "Precinct 9 Blackout",
    authors: ["Jordan Reyes"],
    artists: ["Taylor Voss"],
    status: "completed",
    contentRating: "mature",
    demographic: "none",
    tagIds: ["genre-crime", "genre-thriller"],
    year: 2018,
    description:
      "Six detectives, one city-wide blackout, and a killer who's been using the dark to move bodies for years. A tightly plotted noir that wraps in a satisfying eight volumes.",
    originCountry: "us",
    provider: null,
    favorite: false,
    libraryStatus: "completed",
    communityRating: 8.8,
    userRating: 9,
    chapterCount: 48,
    availableChapters: 0,
    unreadCount: 0,
    lastReadChapter: 48,
    totalChapters: 48,
  },
  {
    id: "static-horizon",
    kind: "comic",
    title: "Static Horizon",
    authors: ["Drew Whitfield"],
    artists: ["Avery Monroe"],
    status: "hiatus",
    contentRating: "safe",
    demographic: "none",
    tagIds: ["genre-sci-fi", "theme-military", "theme-post-apocalyptic"],
    year: 2020,
    description:
      "The last orbital colony loses contact with Earth mid-broadcast, and the survivors have to decide whether silence means catastrophe or quarantine. On hold pending a new artist.",
    originCountry: "gb",
    provider: null,
    favorite: false,
    libraryStatus: "on_hold",
    communityRating: 7.5,
    userRating: null,
    chapterCount: 16,
    availableChapters: 0,
    unreadCount: 4,
    lastReadChapter: 12,
    totalChapters: null,
  },
  {
    id: "vendetta-files",
    kind: "comic",
    title: "The Vendetta Files",
    authors: ["Riley Castillo"],
    artists: ["Quinn Harlan"],
    status: "completed",
    contentRating: "suggestive",
    demographic: "none",
    tagIds: ["genre-mystery", "genre-crime", "format-anthology"],
    year: 2017,
    description:
      "A different unsolved case every arc, one recurring cold-case unit, and a slow-burn frame story that only pays off in the final volume.",
    originCountry: "us",
    provider: null,
    favorite: false,
    libraryStatus: "completed",
    communityRating: 8.2,
    userRating: 7,
    chapterCount: 36,
    availableChapters: 0,
    unreadCount: 0,
    lastReadChapter: 36,
    totalChapters: 36,
  },
  // --- galleries ---
  {
    id: "starlit-chronicles-fan-compilation",
    kind: "gallery",
    title: "Starlit Chronicles — Fan Compilation",
    authors: ["Various Artists"],
    artists: ["Various Artists"],
    status: "ongoing",
    contentRating: "mature",
    demographic: "none",
    tagIds: ["theme-illustration", "theme-fan-art"],
    year: 2023,
    description: "Fan-curated stills from the Starlit Chronicles setting, compiled and cleaned up for offline reading.",
    originCountry: "jp",
    provider: null,
    favorite: false,
    libraryStatus: "none",
    communityRating: 7.7,
    userRating: null,
    chapterCount: 0,
    availableChapters: 0,
    unreadCount: 0,
    lastReadChapter: null,
    totalChapters: null,
    imageCount: 142,
    source: "Starlit Chronicles",
    characters: ["Suzune", "Kagari"],
  },
  {
    id: "aegis-online-doujin-anthology",
    kind: "gallery",
    title: "Aegis Online Doujin Anthology",
    authors: ["Kaito Hoshino"],
    artists: ["Kaito Hoshino"],
    status: "completed",
    contentRating: "erotica",
    demographic: "none",
    tagIds: ["format-doujinshi"],
    year: 2022,
    description:
      "An unofficial doujin anthology set in the Aegis Online universe, collecting several independent circles' takes on the cast.",
    originCountry: "jp",
    provider: null,
    favorite: true,
    libraryStatus: "none",
    communityRating: 8.1,
    userRating: null,
    chapterCount: 0,
    availableChapters: 0,
    unreadCount: 0,
    lastReadChapter: null,
    totalChapters: null,
    imageCount: 58,
    source: "Aegis Online",
    characters: ["Vesper", "Cyra"],
  },
  {
    id: "moonfall-tactics-official-artworks",
    kind: "gallery",
    title: "Moonfall Tactics: Official Artworks",
    authors: ["Moonfall Studio"],
    artists: ["Moonfall Studio"],
    status: "completed",
    contentRating: "suggestive",
    demographic: "none",
    tagIds: ["theme-official", "format-full-color"],
    year: 2021,
    description: "The official art book release for Moonfall Tactics, full-color and cleanly scanned.",
    originCountry: "jp",
    provider: null,
    favorite: false,
    libraryStatus: "none",
    communityRating: 8.9,
    userRating: null,
    chapterCount: 0,
    availableChapters: 0,
    unreadCount: 0,
    lastReadChapter: null,
    totalChapters: null,
    imageCount: 96,
    source: "Moonfall Tactics",
    characters: ["Nozomi", "Mireille", "Aoi"],
  },
  {
    id: "glasswing-idols-cosplay-archive",
    kind: "gallery",
    title: "Glasswing Idols Cosplay Archive",
    authors: ["Various Artists"],
    artists: ["Various Artists"],
    status: "ongoing",
    contentRating: "suggestive",
    demographic: "none",
    tagIds: ["theme-cosplay"],
    year: 2024,
    description:
      "A photo archive following a small convention-circuit cosplay group through several seasons of the Glasswing Idols line.",
    originCountry: "kr",
    provider: null,
    favorite: false,
    libraryStatus: "none",
    communityRating: 7.2,
    userRating: null,
    chapterCount: 0,
    availableChapters: 0,
    unreadCount: 0,
    lastReadChapter: null,
    totalChapters: null,
    imageCount: 74,
    source: "Glasswing Idols",
    characters: ["Rin", "Yumeka"],
  },
];

// --- procedural filler -------------------------------------------------------

function chapterShapeFor(rng: () => number, status: Status): { chapterCount: number; availableChapters: number } {
  if (status === "completed") {
    const total = randInt(rng, 18, 180);
    const gap = chance(rng, 0.3) ? randInt(rng, 1, Math.min(10, total)) : 0;
    return { chapterCount: total - gap, availableChapters: gap };
  }
  if (status === "ongoing") {
    const chapterCount = randInt(rng, 4, 220);
    const availableChapters = chance(rng, 0.45) ? randInt(rng, 1, 6) : 0;
    return { chapterCount, availableChapters };
  }
  // hiatus / cancelled
  const chapterCount = randInt(rng, 6, 90);
  return { chapterCount, availableChapters: chance(rng, 0.1) ? randInt(rng, 1, 2) : 0 };
}

function libraryStatusFor(rng: () => number): LibraryStatus {
  return weighted(rng, [
    [40, "none"],
    [20, "reading"],
    [15, "plan_to_read"],
    [10, "completed"],
    [8, "on_hold"],
    [5, "dropped"],
    [2, "re_reading"],
  ]);
}

function generateFillerManga(count: number, kind: "manga" | "comic", startAt: number, used: Set<string>): SeriesSeed[] {
  const out: SeriesSeed[] = [];
  for (let i = 0; i < count; i++) {
    const idx = startAt + i;
    const rng = rngFor(`${kind}-filler-${idx}`);
    const title = kind === "manga" ? generateMangaTitle(rng, used) : generateComicTitle(rng, used);
    const id = `${kind}-${idx}`;
    const status = weighted<Status>(rng, [
      [50, "ongoing"],
      [30, "completed"],
      [12, "hiatus"],
      [8, "cancelled"],
    ]);
    const originCountry =
      kind === "manga"
        ? weighted(rng, [
            [68, "jp"],
            [22, "kr"],
            [10, "cn"],
          ])
        : weighted(rng, [
            [78, "us"],
            [22, "gb"],
          ]);
    const contentRating = weighted<ContentRating>(rng, [
      [45, "safe"],
      [32, "suggestive"],
      [15, "mature"],
      [8, "erotica"],
    ]);
    const demographic: Demographic =
      kind === "comic" ? "none" : weighted(rng, [
        [30, "shonen"],
        [20, "shojo"],
        [30, "seinen"],
        [20, "josei"],
      ]);
    const tagIds = [
      ...pickN(rng, GENRE_IDS, randInt(rng, 2, 3)),
      ...pickN(rng, THEME_IDS, randInt(rng, 1, 3)),
      ...(chance(rng, 0.3) ? pickN(rng, FORMAT_IDS, 1) : []),
      ...(chance(rng, 0.25) && (contentRating === "mature" || contentRating === "erotica")
        ? pickN(rng, CONTENT_IDS, 1)
        : []),
    ];
    const { chapterCount, availableChapters } = chapterShapeFor(rng, status);
    const libraryStatus = libraryStatusFor(rng);
    const isReadingLike = libraryStatus === "reading" || libraryStatus === "re_reading";
    const unreadCount = isReadingLike ? randInt(rng, 0, Math.min(chapterCount, 15)) : chapterCount > 0 && libraryStatus === "none" ? chapterCount : chance(rng, 0.5) ? randInt(rng, 0, chapterCount) : 0;
    const lastReadChapter =
      libraryStatus === "completed"
        ? chapterCount
        : unreadCount > 0 && unreadCount < chapterCount
          ? chapterCount - unreadCount
          : isReadingLike && chapterCount > 0
            ? Math.max(0, chapterCount - unreadCount)
            : null;
    const provider = kind === "manga" && chance(rng, 0.6) ? "mangadex" : null;
    out.push({
      id,
      kind,
      title,
      authors: [creatorName(rng, originCountry)],
      artists: chance(rng, 0.35) ? [creatorName(rng, originCountry)] : [creatorName(rng, originCountry)],
      status,
      contentRating,
      demographic,
      tagIds,
      year: randInt(rng, 2010, 2026),
      description: "",
      originCountry,
      provider,
      favorite: chance(rng, 0.14),
      libraryStatus,
      communityRating: Math.round((randInt(rng, 50, 98) / 10) * 10) / 10,
      userRating: isReadingLike && chance(rng, 0.4) ? randInt(rng, 6, 10) : null,
      chapterCount,
      availableChapters,
      unreadCount: Math.min(unreadCount, chapterCount),
      lastReadChapter,
      totalChapters: status === "completed" || status === "cancelled" ? chapterCount + availableChapters : null,
    });
  }
  return out;
}

function generateFillerGalleries(count: number, startAt: number, used: Set<string>): SeriesSeed[] {
  const out: SeriesSeed[] = [];
  for (let i = 0; i < count; i++) {
    const idx = startAt + i;
    const rng = rngFor(`gallery-filler-${idx}`);
    const title = generateGalleryTitle(rng, used);
    const originCountry = weighted(rng, [
      [55, "jp"],
      [25, "kr"],
      [20, "us"],
    ]);
    const contentRating = weighted<ContentRating>(rng, [
      [20, "safe"],
      [35, "suggestive"],
      [25, "mature"],
      [20, "erotica"],
    ]);
    const tagIds = pickN(rng, THEME_IDS.filter((t) => ["theme-illustration", "theme-fan-art", "theme-cosplay", "theme-official"].includes(t)), 1).concat(
      chance(rng, 0.4) ? pickN(rng, FORMAT_IDS.filter((f) => f === "format-doujinshi" || f === "format-full-color"), 1) : [],
    );
    out.push({
      id: `gallery-${idx}`,
      kind: "gallery",
      title,
      authors: ["Various Artists"],
      artists: ["Various Artists"],
      status: chance(rng, 0.75) ? "completed" : "ongoing",
      contentRating,
      demographic: "none",
      tagIds: tagIds.length ? tagIds : ["theme-illustration"],
      year: randInt(rng, 2015, 2026),
      description: "",
      originCountry,
      provider: null,
      favorite: chance(rng, 0.12),
      libraryStatus: "none",
      communityRating: Math.round((randInt(rng, 45, 95) / 10) * 10) / 10,
      userRating: null,
      chapterCount: 0,
      availableChapters: 0,
      unreadCount: 0,
      lastReadChapter: null,
      totalChapters: null,
      imageCount: randInt(rng, 24, 220),
      source: chance(rng, 0.7) ? pick(rng, GALLERY_FRANCHISES) : undefined,
      characters: chance(rng, 0.6) ? pickN(rng, GALLERY_CHARACTERS, randInt(rng, 1, 3)) : undefined,
    });
  }
  return out;
}

const usedTitles = new Set<string>(FLAGSHIPS.map((s) => s.title));
const FILLER: SeriesSeed[] = [
  ...generateFillerManga(60, "manga", 1, usedTitles),
  ...generateFillerManga(20, "comic", 1, usedTitles),
  ...generateFillerGalleries(20, 1, usedTitles),
];

// Filler descriptions are generic (kept short and separate from the
// hand-authored blurbs above) so every series still has *something* to show
// in the detail view's synopsis panel.
const GENERIC_BLURBS: Record<Kind, string[]> = {
  manga: [
    "A long-running fan favorite with a dedicated, opinionated readership.",
    "Started as a web series before getting picked up for a full print run.",
    "Known more for its art than its plot, and that's fine by most readers.",
    "A slow-burn series that rewards patience and re-reads.",
  ],
  comic: [
    "An ongoing pull-list staple with a loyal letters-page following.",
    "Started as a creator-owned miniseries before getting extended.",
    "Known for its art team's ever-shifting, experimental style.",
  ],
  gallery: [
    "A community-curated compilation, cleaned up and reorganized for offline reading.",
    "A fan-run archive tracking a small but active circle of artists.",
  ],
};

for (const seed of FILLER) {
  const rng = rngFor(`${seed.id}-blurb`);
  seed.description = pick(rng, GENERIC_BLURBS[seed.kind]);
}

export const seriesSeeds: SeriesSeed[] = [...FLAGSHIPS, ...FILLER];
export const seriesCatalog: SeriesOut[] = seriesSeeds.map(toSeriesOut);

export const DOWNLOAD_DEMO_SERIES_IDS = ["mecha-vandal-zero", "bloodmoon-apothecary"];
