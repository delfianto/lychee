import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import type { BrowseFilters } from "../types";
import FilterPanel from "./FilterPanel.vue";

function emptyFilters(): BrowseFilters {
  return {
    query: "",
    tags: {},
    tagMode: "and",
    ratings: new Set(),
    demographics: new Set(),
    statuses: new Set(),
    readStates: new Set(),
    sort: "",
  };
}

describe("FilterPanel", () => {
  it("emits facet toggles instead of mutating the filters prop", async () => {
    const wrapper = mount(FilterPanel, { props: { filters: emptyFilters() } });

    const safeButton = wrapper.findAll("button").find((b) => b.text() === "Safe");
    await safeButton!.trigger("click"); // first content-rating button
    expect(wrapper.emitted("toggle-rating")).toEqual([["safe"]]);
    // The component only ever displays what it's given via props — it must not have
    // mutated the filters object it was handed (that's the parent's job, on the event).
    expect(wrapper.props("filters").ratings.size).toBe(0);
  });

  it("emits set-tag-mode for the AND/OR toggle", async () => {
    const wrapper = mount(FilterPanel, { props: { filters: emptyFilters() } });
    const [and, or] = wrapper.findAll(".join button");
    await or!.trigger("click");
    expect(wrapper.emitted("set-tag-mode")).toEqual([["or"]]);
    await and!.trigger("click");
    expect(wrapper.emitted("set-tag-mode")![1]).toEqual(["and"]);
  });

  it("emits toggle-tag for a tag chip without mutating props", async () => {
    const filters = emptyFilters();
    const wrapper = mount(FilterPanel, {
      props: {
        filters,
        tagGroups: [{ group: "Genre", tags: [{ id: "t1", name: "Action" }] }],
      },
    });
    const chip = wrapper.findAll("button").find((b) => b.text() === "Action");
    await chip!.trigger("click");
    expect(wrapper.emitted("toggle-tag")).toEqual([["t1"]]);
    expect(filters.tags).toEqual({});
  });
});
