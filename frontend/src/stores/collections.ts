// User collections / reading lists. Backed by a Pinia store so create/rename/
// delete/add/remove persist across navigation; mirrored to localStorage until
// the real API exists (seeded from mocks on first run).

import { defineStore } from "pinia";
import { ref } from "vue";

import { initialCollections } from "../mocks/library";
import type { Collection } from "../types";

const KEY = "lychee.collections";

export const useCollections = defineStore("collections", () => {
  function load(): Collection[] {
    try {
      const raw = localStorage.getItem(KEY);
      if (raw) return JSON.parse(raw) as Collection[];
    } catch {
      /* fall through to seed */
    }
    return initialCollections.map((c) => ({ ...c, seriesIds: [...c.seriesIds] }));
  }

  const lists = ref<Collection[]>(load());

  function persist(): void {
    localStorage.setItem(KEY, JSON.stringify(lists.value));
  }

  function getList(id: string): Collection | undefined {
    return lists.value.find((l) => l.id === id);
  }
  function createList(name: string): Collection {
    const c: Collection = { id: `l${Date.now()}`, name: name.trim() || "Untitled list", seriesIds: [] };
    lists.value.push(c);
    persist();
    return c;
  }
  function renameList(id: string, name: string): void {
    const c = getList(id);
    if (c && name.trim()) {
      c.name = name.trim();
      persist();
    }
  }
  function deleteList(id: string): void {
    lists.value = lists.value.filter((l) => l.id !== id);
    persist();
  }
  function hasSeries(listId: string, seriesId: string): boolean {
    return getList(listId)?.seriesIds.includes(seriesId) ?? false;
  }
  function toggleSeries(listId: string, seriesId: string): void {
    const c = getList(listId);
    if (!c) return;
    const i = c.seriesIds.indexOf(seriesId);
    if (i >= 0) c.seriesIds.splice(i, 1);
    else c.seriesIds.push(seriesId);
    persist();
  }
  function removeSeries(listId: string, seriesId: string): void {
    const c = getList(listId);
    if (!c) return;
    c.seriesIds = c.seriesIds.filter((s) => s !== seriesId);
    persist();
  }

  return { lists, getList, createList, renameList, deleteList, hasSeries, toggleSeries, removeSeries };
});
