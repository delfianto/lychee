// User collections / reading lists, backed by the API. Keeps a reactive in-memory
// `lists` (so hasSeries stays synchronous for templates) and mutates optimistically
// while persisting to the server.

import { defineStore } from "pinia";
import { ref } from "vue";

import { api } from "../api/client";
import type { Collection } from "../types";

interface ApiCollection {
  id: string;
  name: string;
  description?: string | null;
  seriesIds: string[];
}

function toCollection(c: ApiCollection): Collection {
  return { id: c.id, name: c.name, description: c.description ?? undefined, seriesIds: c.seriesIds };
}

export const useCollections = defineStore("collections", () => {
  const lists = ref<Collection[]>([]);

  async function refresh(): Promise<void> {
    const { data } = await api.GET("/api/collections");
    lists.value = (data ?? []).map(toCollection);
  }
  void refresh();

  function getList(id: string): Collection | undefined {
    return lists.value.find((l) => l.id === id);
  }

  async function createList(name: string): Promise<Collection | undefined> {
    const { data } = await api.POST("/api/collections", {
      body: { name: name.trim() || "Untitled list" },
    });
    if (!data) return undefined;
    const created = toCollection(data);
    lists.value.push(created);
    return created;
  }

  async function renameList(id: string, name: string): Promise<void> {
    const list = getList(id);
    if (!list || !name.trim()) return;
    list.name = name.trim();
    await api.PATCH("/api/collections/{collection_id}", {
      params: { path: { collection_id: id } },
      body: { name: list.name },
    });
  }

  async function deleteList(id: string): Promise<void> {
    lists.value = lists.value.filter((l) => l.id !== id);
    await api.DELETE("/api/collections/{collection_id}", {
      params: { path: { collection_id: id } },
    });
  }

  function hasSeries(listId: string, seriesId: string): boolean {
    return getList(listId)?.seriesIds.includes(seriesId) ?? false;
  }

  async function toggleSeries(listId: string, seriesId: string): Promise<void> {
    const list = getList(listId);
    if (!list) return;
    const index = list.seriesIds.indexOf(seriesId);
    if (index >= 0) {
      list.seriesIds.splice(index, 1);
      await api.DELETE("/api/collections/{collection_id}/series/{series_id}", {
        params: { path: { collection_id: listId, series_id: seriesId } },
      });
    } else {
      list.seriesIds.push(seriesId);
      await api.POST("/api/collections/{collection_id}/series", {
        params: { path: { collection_id: listId } },
        body: { seriesId },
      });
    }
  }

  async function removeSeries(listId: string, seriesId: string): Promise<void> {
    const list = getList(listId);
    if (!list) return;
    list.seriesIds = list.seriesIds.filter((s) => s !== seriesId);
    await api.DELETE("/api/collections/{collection_id}/series/{series_id}", {
      params: { path: { collection_id: listId, series_id: seriesId } },
    });
  }

  return {
    lists,
    refresh,
    getList,
    createList,
    renameList,
    deleteList,
    hasSeries,
    toggleSeries,
    removeSeries,
  };
});
