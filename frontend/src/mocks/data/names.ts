// Word banks + generators for procedurally filled-out series: creator names,
// scanlation groups, and title templates. Everything here is fictional —
// no real manga/comic titles or real people — generated to give the library
// a realistic *shape* (volume, variety) rather than to resemble any one work.

import { type Rng, pick, pickN } from "../utils";

const JP_GIVEN = [
  "Hiroshi",
  "Yuki",
  "Kenji",
  "Aiko",
  "Sora",
  "Haruto",
  "Nanami",
  "Ren",
  "Akira",
  "Mei",
  "Takeshi",
  "Yui",
  "Daichi",
  "Sakura",
  "Kaito",
  "Emi",
  "Souta",
  "Riko",
];
const JP_SURNAME = [
  "Tanaka",
  "Yamamoto",
  "Kobayashi",
  "Sato",
  "Watanabe",
  "Ito",
  "Nakamura",
  "Fujii",
  "Okada",
  "Matsumoto",
  "Inoue",
  "Hoshino",
  "Kurosawa",
  "Endo",
  "Kishida",
  "Arakawa",
];
const KR_GIVEN = ["Ji-ho", "Seo-yeon", "Min-jun", "Ha-eun", "Do-yun", "Yerin", "Joon", "Somi", "Hyun-woo", "Areum"];
const KR_SURNAME = ["Kim", "Lee", "Park", "Choi", "Jung", "Kang", "Yoon", "Han", "Oh", "Seo"];
const CN_GIVEN = ["Wei", "Mei", "Jun", "Ling", "Hao", "Xin", "Yan", "Feng", "Lian", "Chen"];
const CN_SURNAME = ["Wang", "Li", "Zhang", "Liu", "Chen", "Yang", "Zhao", "Wu", "Sun", "Zhou"];
const WEST_GIVEN = ["Alex", "Morgan", "Jordan", "Casey", "Riley", "Sam", "Taylor", "Drew", "Quinn", "Avery", "Rowan"];
const WEST_SURNAME = [
  "Sterling",
  "Blackwood",
  "Reyes",
  "Whitfield",
  "Monroe",
  "Castillo",
  "Harlan",
  "Voss",
  "Marsh",
  "Delgado",
];

const POOLS: Record<string, { given: readonly string[]; surname: readonly string[] }> = {
  jp: { given: JP_GIVEN, surname: JP_SURNAME },
  kr: { given: KR_GIVEN, surname: KR_SURNAME },
  cn: { given: CN_GIVEN, surname: CN_SURNAME },
  us: { given: WEST_GIVEN, surname: WEST_SURNAME },
  gb: { given: WEST_GIVEN, surname: WEST_SURNAME },
};

export function creatorName(rng: Rng, origin: string): string {
  const pool = POOLS[origin] ?? POOLS.jp;
  if (!pool) throw new Error("name pool missing");
  return `${pick(rng, pool.given)} ${pick(rng, pool.surname)}`;
}

export const SCANLATION_GROUPS = [
  "Moonlit Scans",
  "Iron Lotus TL",
  "Kagehana Fansub",
  "Rustling Pages",
  "Nightowl Scanlations",
  "Paper Crane Group",
  "Static Ink",
  "Silver Quill Scans",
  "Northlight TL",
  "Amber Frame Scans",
  "Wandering Brush",
  "Echo Chapter Team",
];

export const GALLERY_FRANCHISES = [
  "Starlit Chronicles",
  "Aegis Online",
  "Moonfall Tactics",
  "Crimson Requiem",
  "Neko Café Days",
  "Ashen Vale",
  "Prism Drift",
  "Voidrunner Academy",
  "Emberfall Saga",
  "Glasswing Idols",
];

export const GALLERY_CHARACTERS = [
  "Suzune",
  "Kagari",
  "Elrin",
  "Nozomi",
  "Vesper",
  "Chiyoko",
  "Rin",
  "Mireille",
  "Aoi",
  "Sable",
  "Yumeka",
  "Cyra",
  "Hikage",
  "Lys",
  "Tsumugi",
];

// --- title generation -----------------------------------------------------

const MANGA_ADJ = [
  "Silent",
  "Crimson",
  "Broken",
  "Eternal",
  "Forgotten",
  "Radiant",
  "Hollow",
  "Wandering",
  "Sacred",
  "Shattered",
  "Frozen",
  "Burning",
  "Lost",
  "Whispering",
  "Golden",
  "Iron",
  "Faded",
  "Endless",
  "Twilight",
  "Savage",
];
const MANGA_NOUN = [
  "Blade",
  "Kingdom",
  "Academy",
  "Oracle",
  "Throne",
  "Wolf",
  "Garden",
  "Requiem",
  "Covenant",
  "Labyrinth",
  "Symphony",
  "Empire",
  "Prophecy",
  "Heart",
  "Legion",
  "Shrine",
  "Abyss",
  "Chronicle",
  "Dominion",
  "Star",
];
const MANGA_SUB = ["Reborn", "Chronicles", "Genesis", "Requiem", "Awakening", "Overture", "Aftermath", "Origins"];

const COMIC_ADJ = ["Midnight", "Steel", "Neon", "Rogue", "Shattered", "Last", "Ghost", "Wired", "Fallout", "Static"];
const COMIC_NOUN = [
  "Vanguard",
  "Precinct",
  "Syndicate",
  "Horizon",
  "Protocol",
  "Requiem",
  "Outpost",
  "Vendetta",
  "Circuit",
  "Verdict",
];

function unique(rng: Rng, used: Set<string>, make: () => string): string {
  for (let attempt = 0; attempt < 12; attempt++) {
    const title = make();
    if (!used.has(title)) {
      used.add(title);
      return title;
    }
  }
  const fallback = `${make()} (${Math.floor(rng() * 900 + 100)})`;
  used.add(fallback);
  return fallback;
}

export function generateMangaTitle(rng: Rng, used: Set<string>): string {
  const templates = [
    () => `${pick(rng, MANGA_ADJ)} ${pick(rng, MANGA_NOUN)}`,
    () => `The ${pick(rng, MANGA_ADJ)} ${pick(rng, MANGA_NOUN)}`,
    () => `${pick(rng, MANGA_NOUN)} of the ${pick(rng, MANGA_ADJ)} ${pick(rng, MANGA_NOUN)}`,
    () => `${pick(rng, MANGA_ADJ)} ${pick(rng, MANGA_NOUN)}: ${pick(rng, MANGA_SUB)}`,
  ];
  return unique(rng, used, pick(rng, templates));
}

export function generateComicTitle(rng: Rng, used: Set<string>): string {
  const templates = [
    () => `${pick(rng, COMIC_ADJ)} ${pick(rng, COMIC_NOUN)}`,
    () => `${pick(rng, COMIC_NOUN)}: ${pick(rng, COMIC_ADJ)} Hour`,
    () => `The ${pick(rng, COMIC_NOUN)} Files`,
    () => `${pick(rng, COMIC_ADJ)} ${pick(rng, COMIC_NOUN)} Vol. ${1 + Math.floor(rng() * 4)}`,
  ];
  return unique(rng, used, pick(rng, templates));
}

export function generateGalleryTitle(rng: Rng, used: Set<string>): string {
  const templates = [
    () => `${pick(rng, GALLERY_FRANCHISES)} — Fan Compilation`,
    () => `${pick(rng, pickN(rng, GALLERY_CHARACTERS, 1))} Private Sketches`,
    () => `${pick(rng, GALLERY_FRANCHISES)} Doujin Anthology`,
    () => `${creatorName(rng, "jp")} Artworks Vol. ${1 + Math.floor(rng() * 6)}`,
  ];
  return unique(rng, used, pick(rng, templates));
}
