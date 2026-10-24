// User collections / reading lists, backed by the API. Keeps a reactive in-memory
// `lists` (so hasSeries stays synchronous for templates) and mutates optimistically
// while persisting to the server.

import { defineStore } from "pinia";
import { ref, onScopeDispose } from "vue";
import { onTaskDone } from "../api/events";
import { apiErrorMessage } from "../api/queries";

import { api } from "../api/client";
import type { Collection } from "../types";

interface ApiCollection extends Omit<Collection, "description" | "kind"> {
  id: string;
  name: string;
  description?: string | null;
  seriesIds: string[];
  kind?: string | null;
}

function toCollection(c: ApiCollection): Collection {
  return {
    ...c,
    id: c.id,
    name: c.name,
    description: c.description ?? undefined,
    seriesIds: c.seriesIds,
    kind: (c.kind ?? undefined) as Collection["kind"],
  };
}

export const useCollections = defineStore("collections", () => {
  const lists = ref<Collection[]>([]);

  async function refresh(): Promise<void> {
    const { data } = await api.GET("/api/collections");
    lists.value = (data ?? []).map(toCollection);
  }
  void refresh();
  onScopeDispose(
    onTaskDone((task) => {
      if (task.status === "done" && ["mdlist", "import"].includes(task.kind)) void refresh();
    }),
  );

  function getList(id: string): Collection | undefined {
    return lists.value.find((l) => l.id === id);
  }

  async function createList(
    name: string,
    options?: {
      kind?: "manga" | "comic" | "gallery";
      provider?: "mangadex";
      visibility?: "public" | "private";
    },
  ): Promise<Collection | undefined> {
    const { data, error } = await api.POST("/api/collections", {
      body: {
        name: name.trim() || "Untitled list",
        kind: "manga",
        visibility: "private",
        ...options,
      },
    });
    if (error) throw new Error(apiErrorMessage(error, "Couldn't create list"));
    if (!data) return undefined;
    const created = toCollection(data);
    lists.value.push(created);
    return created;
  }

  async function renameList(id: string, name: string): Promise<void> {
    const list = getList(id);
    if (!list || !name.trim()) return;
    const { error } = await api.PATCH("/api/collections/{collection_id}", {
      params: { path: { collection_id: id } },
      body: { name: name.trim() },
    });
    if (error) throw new Error(apiErrorMessage(error, "Couldn't rename list"));
    list.name = name.trim();
  }

  async function deleteList(id: string, remote = false): Promise<void> {
    const { error } = await api.DELETE("/api/collections/{collection_id}", {
      params: { path: { collection_id: id }, ...(remote ? { query: { remote: true } } : {}) },
    });
    if (error) throw new Error(apiErrorMessage(error, "Couldn't delete list"));
    lists.value = lists.value.filter((l) => l.id !== id);
  }

  function hasSeries(listId: string, seriesId: string): boolean {
    return getList(listId)?.seriesIds.includes(seriesId) ?? false;
  }

  async function toggleSeries(listId: string, seriesId: string): Promise<void> {
    const list = getList(listId);
    if (!list) return;
    const index = list.seriesIds.indexOf(seriesId);
    if (index >= 0) {
      const { error } = await api.DELETE("/api/collections/{collection_id}/series/{series_id}", {
        params: { path: { collection_id: listId, series_id: seriesId } },
      });
      if (error) throw new Error(apiErrorMessage(error, "Couldn't remove from list"));
      list.seriesIds.splice(index, 1);
    } else {
      const { error } = await api.POST("/api/collections/{collection_id}/series", {
        params: { path: { collection_id: listId } },
        body: { seriesId },
      });
      if (error) throw new Error(apiErrorMessage(error, "Couldn't add to list"));
      list.seriesIds.push(seriesId);
    }
  }

  async function removeSeries(listId: string, seriesId: string): Promise<void> {
    const list = getList(listId);
    if (!list) return;
    const { error } = await api.DELETE("/api/collections/{collection_id}/series/{series_id}", {
      params: { path: { collection_id: listId, series_id: seriesId } },
    });
    if (error) throw new Error(apiErrorMessage(error, "Couldn't remove from list"));
    list.seriesIds = list.seriesIds.filter((s) => s !== seriesId);
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
