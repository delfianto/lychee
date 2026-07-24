// Client-side sort for the mock series lists. Mirrors the sort dropdown labels;
// "Recently Added/Updated" keep source order until the API provides timestamps.

import type { Series } from "../types";

export function sortSeries(list: Series[], sort: string): Series[] {
  const arr = [...list];
  switch (sort) {
    case "Title":
      return arr.sort((a, b) => a.title.localeCompare(b.title));
    case "Rating":
      return arr.sort((a, b) => (b.rating ?? 0) - (a.rating ?? 0));
    case "Unread":
      return arr.sort((a, b) => b.unreadCount - a.unreadCount);
    default:
      return arr; // Recently Added / Recently Updated → source order (mock)
  }
}
