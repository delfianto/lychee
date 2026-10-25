import type { LocationQuery, RouteLocationRaw } from "vue-router";
import type { ContentRating, Demographic, PublicationStatus, Series } from "../types";

type MetadataFilter = "ratings" | "demographics" | "pubStatus" | "tags";

/** Browse within the work's media kind, using taxonomy IDs rather than display labels. */
export function metadataBrowseLink(
  series: Pick<Series, "kind">,
  filter: MetadataFilter,
  value: string,
): RouteLocationRaw {
  return { path: series.kind === "comic" ? "/comics" : "/manga", query: { [filter]: value } };
}

function values(query: LocationQuery, key: MetadataFilter): string[] {
  const raw = query[key];
  return (Array.isArray(raw) ? raw : [raw])
    .flatMap((value) => value?.split(",") ?? [])
    .map((value) => value.trim())
    .filter(Boolean);
}

function allowed<T extends string>(values: string[], choices: readonly T[]): Set<T> {
  return new Set(values.filter((value): value is T => choices.some((choice) => choice === value)));
}

/** Metadata deep links seed the same controls used by the advanced filter form. */
export function metadataBrowseFilters(query: LocationQuery) {
  return {
    ratings: allowed<ContentRating>(values(query, "ratings"), [
      "safe",
      "suggestive",
      "erotica",
      "pornographic",
      "explicit",
    ]),
    demographics: allowed<Demographic>(values(query, "demographics"), [
      "none",
      "shonen",
      "shojo",
      "seinen",
      "josei",
    ]),
    statuses: allowed<PublicationStatus>(values(query, "pubStatus"), [
      "ongoing",
      "completed",
      "hiatus",
      "cancelled",
    ]),
    tags: Object.fromEntries(
      values(query, "tags")
        .filter((value) => value !== "-")
        .map((value) =>
          value.startsWith("-")
            ? [value.slice(1), "exclude" as const]
            : [value, "include" as const],
        ),
    ),
  };
}
