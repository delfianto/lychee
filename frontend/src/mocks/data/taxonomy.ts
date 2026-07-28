// Taxonomy vocabulary — mirrors backend/src/taxonomy/seed.py so the filter
// panel, Content settings tab, and per-series tags all agree on the same ids.

import type { components } from "../../api/schema";
import { slugify } from "../utils";

type TaxonomyItem = components["schemas"]["TaxonomyItemOut"];
type Tag = components["schemas"]["TagOut"];
type SeriesOut = components["schemas"]["SeriesOut"];

const GENRES = [
  "action",
  "adventure",
  "boys-love",
  "comedy",
  "crime",
  "drama",
  "fantasy",
  "girls-love",
  "historical",
  "horror",
  "isekai",
  "mecha",
  "medical",
  "mystery",
  "philosophical",
  "psychological",
  "romance",
  "sci-fi",
  "slice-of-life",
  "sports",
  "superhero",
  "thriller",
  "tragedy",
  "wuxia",
] as const;

const THEMES = [
  "aliens",
  "animals",
  "cooking",
  "demons",
  "harem",
  "mafia",
  "magic",
  "magical-girls",
  "martial-arts",
  "military",
  "monsters",
  "music",
  "ninja",
  "office-workers",
  "police",
  "post-apocalyptic",
  "reincarnation",
  "reverse-harem",
  "samurai",
  "school-life",
  "supernatural",
  "survival",
  "time-travel",
  "vampires",
  "video-games",
  "villainess",
  "virtual-reality",
  "zombies",
  "illustration",
  "fan-art",
  "cosplay",
  "official",
] as const;

const FORMATS = [
  "4-koma",
  "adaptation",
  "anthology",
  "award-winning",
  "doujinshi",
  "fan-colored",
  "full-color",
  "long-strip",
  "official-colored",
  "oneshot",
  "self-published",
  "web-comic",
] as const;

const CONTENT = ["gore", "sexual-violence"] as const;
export const CONTENT_RATINGS = ["safe", "suggestive", "erotica", "pornographic", "explicit"] as const;
export const DEMOGRAPHICS = ["shonen", "shojo", "seinen", "josei"] as const;

const DISPLAY_OVERRIDES: Record<string, string> = {
  "sci-fi": "Sci-Fi",
  "boys-love": "Boys' Love",
  "girls-love": "Girls' Love",
  "4-koma": "4-Koma",
  "post-apocalyptic": "Post-Apocalyptic",
};

function humanize(slug: string): string {
  return DISPLAY_OVERRIDES[slug] ?? slug.split("-").map((w) => w[0]?.toUpperCase() + w.slice(1)).join(" ");
}

interface DefAlias {
  id: string;
  name: string;
}
interface Def {
  id: string;
  name: string;
  category: string;
  system: boolean;
  aliases: DefAlias[];
}

function defs(slugs: readonly string[], category: string, system = false): Def[] {
  return slugs.map((slug) => ({
    id: `${category}-${slug}`,
    name: humanize(slug),
    category,
    system,
    aliases: [],
  }));
}

const ALL_DEFS: Def[] = [
  ...defs(GENRES, "genre"),
  ...defs(THEMES, "theme"),
  ...defs(FORMATS, "format"),
  ...defs(CONTENT, "content"),
  ...defs(CONTENT_RATINGS, "content_rating", true),
  ...defs(DEMOGRAPHICS, "demographic", true),
];

const BY_ID = new Map(ALL_DEFS.map((d) => [d.id, d]));

export function tag(id: string): Tag {
  const d = BY_ID.get(id);
  if (!d) throw new Error(`Unknown taxonomy id: ${id}`);
  return { id: d.id, name: d.name, group: d.category };
}

export const GENRE_IDS = GENRES.map((s) => `genre-${s}`);
export const THEME_IDS = THEMES.map((s) => `theme-${s}`);
export const FORMAT_IDS = FORMATS.map((s) => `format-${s}`);
export const CONTENT_IDS = CONTENT.map((s) => `content-${s}`);

// A couple of rows start disabled so the Content settings tab has something
// to demonstrate the enable/disable toggle against.
const DISABLED_AT_SEED = new Set(["format-self-published", "content-sexual-violence", "theme-reverse-harem"]);

let extraTags: Def[] = [];

/** Seed data mutates this list (create/delete) — handlers read/write through here. */
export function allTaxonomyDefs(): Def[] {
  return [...ALL_DEFS, ...extraTags];
}

export function addTaxonomyDef(def: Def): void {
  extraTags.push(def);
  BY_ID.set(def.id, def);
}

export function removeTaxonomyDef(id: string): boolean {
  const before = extraTags.length;
  extraTags = extraTags.filter((d) => d.id !== id);
  return extraTags.length !== before;
}

export function renameTaxonomyDef(id: string, name: string): boolean {
  const d = BY_ID.get(id);
  if (!d) return false;
  d.name = name;
  return true;
}

export function addAliasToDef(tagId: string, name: string): DefAlias | null {
  const d = BY_ID.get(tagId);
  if (!d) return null;
  const alias: DefAlias = { id: slugify(name), name };
  if (!d.aliases.some((a) => a.id === alias.id)) d.aliases.push(alias);
  return alias;
}

export function removeAliasFromDef(tagId: string, aliasId: string): boolean {
  const d = BY_ID.get(tagId);
  if (!d) return false;
  const before = d.aliases.length;
  d.aliases = d.aliases.filter((a) => a.id !== aliasId);
  return d.aliases.length !== before;
}

const disabledIds = new Set(DISABLED_AT_SEED);
export function setTaxonomyEnabled(id: string, enabled: boolean): void {
  if (enabled) disabledIds.delete(id);
  else disabledIds.add(id);
}
export function isTaxonomyEnabled(id: string): boolean {
  return !disabledIds.has(id);
}

/** Build the OffsetPage payload, deriving `uses` from the live series catalog. */
export function buildTaxonomyItems(seriesList: readonly SeriesOut[]): TaxonomyItem[] {
  const uses = new Map<string, number>();
  const bump = (id: string) => uses.set(id, (uses.get(id) ?? 0) + 1);
  for (const s of seriesList) {
    for (const t of s.tags) bump(t.id);
    bump(`content_rating-${s.contentRating}`);
    if (s.demographic !== "none") bump(`demographic-${s.demographic}`);
  }
  return allTaxonomyDefs().map((d) => ({
    id: d.id,
    name: d.name,
    category: d.category,
    uses: uses.get(d.id) ?? 0,
    enabled: isTaxonomyEnabled(d.id),
    system: d.system,
    aliases: d.aliases.map((a) => ({ id: a.id, name: a.name, tagId: d.id })),
  }));
}
