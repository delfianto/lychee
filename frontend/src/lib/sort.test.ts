import { describe, expect, it } from "vitest";

import type { Series } from "../types";
import { sortSeries } from "./sort";

function series(overrides: Partial<Series> & Pick<Series, "id">): Series {
  return {
    title: overrides.id,
    coverUrl: "",
    authors: [],
    artists: [],
    status: "ongoing",
    contentRating: "safe",
    demographic: "none",
    tags: [],
    chapterCount: 0,
    unreadCount: 0,
    favorite: false,
    ...overrides,
  };
}

describe("sortSeries", () => {
  it("sorts by title (localeCompare, ascending)", () => {
    const list = [series({ id: "b", title: "Berserk" }), series({ id: "a", title: "Akira" })];
    expect(sortSeries(list, "Title").map((s) => s.id)).toEqual(["a", "b"]);
  });

  it("sorts by rating, descending, treating missing rating as 0", () => {
    const list = [
      series({ id: "low", rating: 2 }),
      series({ id: "unrated" }),
      series({ id: "high", rating: 9 }),
    ];
    expect(sortSeries(list, "Rating").map((s) => s.id)).toEqual(["high", "low", "unrated"]);
  });

  it("sorts by unread count, descending", () => {
    const list = [series({ id: "few", unreadCount: 1 }), series({ id: "many", unreadCount: 20 })];
    expect(sortSeries(list, "Unread").map((s) => s.id)).toEqual(["many", "few"]);
  });

  it("leaves source order unchanged for an unknown/default sort key", () => {
    const list = [series({ id: "z" }), series({ id: "a" })];
    expect(sortSeries(list, "Recently Added").map((s) => s.id)).toEqual(["z", "a"]);
  });

  it("does not mutate the input array", () => {
    const list = [series({ id: "b", title: "B" }), series({ id: "a", title: "A" })];
    const original = [...list];
    sortSeries(list, "Title");
    expect(list).toEqual(original);
  });
});
