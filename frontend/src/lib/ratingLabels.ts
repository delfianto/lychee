// Reactive content-rating/demographic display labels, sourced from the live
// taxonomy so a rename in Settings → Content (e.g. "Mature" → "Hentai") shows
// up everywhere a rating/demographic badge is rendered — not just once the
// page happens to reload. See notes/09-tag-aliases.md ("Display label
// editability"): the sync key (Tag.id, e.g. "mature") never changes; only the
// display label does, and that's what this module resolves.
//
// Falls back to the static defaults in display.ts until the fetch resolves
// (or if it fails), so nothing renders blank on first paint.

import { ref } from "vue";

import type { ContentRating, Demographic } from "../types";
import { fetchRatingLabels } from "../api/queries";
import { contentRatingLabel as defaultContentRatingLabel } from "./display";

const defaultDemographicLabel: Record<Demographic, string> = {
  none: "None",
  shonen: "Shonen",
  shojo: "Shojo",
  seinen: "Seinen",
  josei: "Josei",
};

const contentRatingNames = ref<Record<string, string>>({ ...defaultContentRatingLabel });
const demographicNames = ref<Record<string, string>>({ ...defaultDemographicLabel });
let loadStarted = false;

/** Fetch once per app session (called from AppShell); safe to call again — a
 * failed attempt is allowed to retry, a successful one is a no-op. */
export async function ensureRatingLabelsLoaded(): Promise<void> {
  if (loadStarted) return;
  loadStarted = true;
  try {
    const { contentRating, demographic } = await fetchRatingLabels();
    Object.assign(contentRatingNames.value, contentRating);
    Object.assign(demographicNames.value, demographic);
  } catch {
    loadStarted = false;
  }
}

export function ratingLabel(id: ContentRating): string {
  return contentRatingNames.value[id] ?? defaultContentRatingLabel[id];
}

export function demographicLabel(id: Demographic): string {
  return demographicNames.value[id] ?? defaultDemographicLabel[id];
}
