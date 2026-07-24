// Shared display mappings for series metadata, so the status dot, rating badge,
// and content-rating badge look identical everywhere they appear (library cards,
// series detail, browse).

import type { ContentRating, PublicationStatus } from "../types";

/** Publication status → a low-noise colored dot (bg-* token) + human label. */
export const statusColor: Record<PublicationStatus, string> = {
  ongoing: "bg-success",
  completed: "bg-info",
  hiatus: "bg-warning",
  cancelled: "bg-error",
};

export const statusLabel: Record<PublicationStatus, string> = {
  ongoing: "Ongoing",
  completed: "Completed",
  hiatus: "Hiatus",
  cancelled: "Cancelled",
};

/** Content rating (how explicit) → badge color + label. */
export const contentRatingClass: Record<ContentRating, string> = {
  safe: "badge-ghost",
  suggestive: "badge-warning",
  erotica: "badge-accent",
  mature: "badge-error",
};

export const contentRatingLabel: Record<ContentRating, string> = {
  safe: "Safe",
  suggestive: "Suggestive",
  erotica: "Erotica",
  mature: "Mature",
};
