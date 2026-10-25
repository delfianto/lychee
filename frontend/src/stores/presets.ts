import { defineStore } from "pinia";
import { ref, watch } from "vue";
import type { BrowseFilters, ContentRating, Demographic, PublicationStatus } from "../types";

export interface BrowsePreset {
  name: string;
  query: string;
  tags: Record<string, "include" | "exclude">;
  tagMode: "and" | "or";
  author?: string;
  artist?: string;
  ratings: ContentRating[];
  demographics: Demographic[];
  statuses: PublicationStatus[];
  readStates: string[];
}

export function presetFilters(preset: BrowsePreset): BrowseFilters {
  return {
    query: preset.query ?? "",
    author: preset.author ?? "",
    artist: preset.artist ?? "",
    tags: { ...preset.tags },
    tagMode: preset.tagMode === "or" ? "or" : "and",
    ratings: new Set(preset.ratings),
    demographics: new Set(preset.demographics),
    statuses: new Set(preset.statuses),
    readStates: new Set(preset.readStates),
    sort: "",
  };
}

export const usePresets = defineStore("presets", () => {
  function load(): BrowsePreset[] {
    try {
      const value: unknown = JSON.parse(localStorage.getItem("lychee.presets") ?? "[]");
      return Array.isArray(value)
        ? value.filter(
            (p): p is BrowsePreset => !!p && typeof p === "object" && typeof p.name === "string",
          )
        : [];
    } catch {
      return [];
    }
  }
  const presets = ref<BrowsePreset[]>(load());
  watch(presets, (value) => localStorage.setItem("lychee.presets", JSON.stringify(value)), {
    deep: true,
  });
  function save(preset: BrowsePreset): void {
    const index = presets.value.findIndex((p) => p.name === preset.name);
    if (index < 0) presets.value.push(preset);
    else presets.value[index] = preset;
  }
  function remove(name: string): void {
    presets.value = presets.value.filter((p) => p.name !== name);
  }
  return { presets, save, remove };
});
