// Curated "lists" (collections) — a handful of named groupings over the
// series catalog, exercising both single-kind and mixed-kind lists.

import type { components } from "../../api/schema";
import { seriesCatalog } from "./series";

type CollectionOut = components["schemas"]["CollectionOut"];

function idsFor(...titles: string[]): string[] {
  return titles
    .map((title) => seriesCatalog.find((s) => s.title === title)?.id)
    .filter((id): id is string => Boolean(id));
}

interface CollectionSeed {
  id: string;
  name: string;
  description: string | null;
  seriesIds: string[];
}

const SEEDS: CollectionSeed[] = [
  {
    id: "list-currently-reading",
    name: "Currently Reading",
    description: "Everything with a bookmark in it right now.",
    seriesIds: idsFor(
      "Nightfall Requiem",
      "Glass Menagerie High",
      "Wraith of the Nine Tails",
      "Tender Static",
      "Mecha Vandal Zero",
      "Twelve Steps to Ruin",
      "Bloodmoon Apothecary",
    ),
  },
  {
    id: "list-completed-masterpieces",
    name: "Completed Masterpieces",
    description: "Finished series worth recommending without hedging.",
    seriesIds: idsFor("The Cartographer's Daughter", "Court of Hollow Petals", "The Last Cicada Summer"),
  },
  {
    id: "list-weekend-binge",
    name: "Weekend Binge",
    description: "Short enough to finish in a couple of sittings.",
    seriesIds: idsFor("Static Hearts", "Iron Bloom"),
  },
  {
    id: "list-hidden-gems",
    name: "Hidden Gems",
    description: null,
    seriesIds: idsFor("Silverleaf Testament", "Twelve Steps to Ruin"),
  },
  {
    id: "list-comic-pull",
    name: "Comic Pull List",
    description: "What's on order down at the shop.",
    seriesIds: idsFor("Vanguard Protocol", "Precinct 9 Blackout", "Static Horizon", "The Vendetta Files"),
  },
  {
    id: "list-art-favorites",
    name: "Art Favorites",
    description: "Gallery folders worth revisiting.",
    seriesIds: idsFor(
      "Moonfall Tactics: Official Artworks",
      "Starlit Chronicles — Fan Compilation",
      "Aegis Online Doujin Anthology",
    ),
  },
  {
    id: "list-mixed-shelf",
    name: "Recommend to a Friend",
    description: "One of each kind, for when someone asks where to start.",
    seriesIds: idsFor("Wraith of the Nine Tails", "Vanguard Protocol", "Glasswing Idols Cosplay Archive"),
  },
];

export function kindFor(seriesIds: string[]): string | null {
  const kinds = new Set(
    seriesIds.map((id) => seriesCatalog.find((s) => s.id === id)?.kind).filter((k): k is string => Boolean(k)),
  );
  if (kinds.size === 0) return null;
  if (kinds.size > 1) return "mixed";
  return [...kinds][0] ?? null;
}

export const collectionsDb: CollectionOut[] = SEEDS.map((seed) => ({
  id: seed.id,
  name: seed.name,
  description: seed.description,
  seriesIds: seed.seriesIds,
  kind: kindFor(seed.seriesIds),
}));
