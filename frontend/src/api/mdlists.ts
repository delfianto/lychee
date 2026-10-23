import { api } from "./client";
import { apiErrorMessage } from "./queries";
import type { components } from "./schema";

export type MDListChapter = components["schemas"]["ListChapterOut"];
export type MDListInfo = components["schemas"]["RemoteListOut"];
export async function importMDList(reference: string) {
  const { data, error } = await api.POST("/api/collections/mangadex/import", {
    body: { reference },
  });
  if (error || !data) throw new Error(apiErrorMessage(error, "Couldn't import MangaDex list"));
  return data;
}
export async function syncMDLists(id?: string) {
  const result = id
    ? await api.POST("/api/collections/{collection_id}/sync", {
        params: { path: { collection_id: id } },
      })
    : await api.POST("/api/collections/mangadex/sync");
  if (result.error || !result.data)
    throw new Error(apiErrorMessage(result.error, "Couldn't sync MangaDex lists"));
  return result.data;
}
export async function browseMDLists(reference: string) {
  let id = reference.trim();
  if (id.startsWith("https://")) {
    const url = new URL(id);
    if (
      !["mangadex.org", "www.mangadex.org"].includes(url.hostname) ||
      !url.pathname.startsWith("/user/")
    )
      throw new Error("Use a MangaDex user URL or UUID");
    id = url.pathname.split("/")[2]!;
  }
  const { data, error } = await api.GET("/api/collections/mangadex/users/{reference}/lists", {
    params: { path: { reference: id } },
  });
  if (error || !data) throw new Error(apiErrorMessage(error, "Couldn't load public lists"));
  return data;
}
export async function followMDList(id: string, followed: boolean) {
  const { error } = await api.PUT("/api/collections/{collection_id}/follow", {
    params: { path: { collection_id: id } },
    body: { followed },
  });
  if (error) throw new Error(apiErrorMessage(error, "Couldn't update list follow"));
}
export async function setListVisibility(id: string, visibility: "public" | "private") {
  const { error } = await api.PATCH("/api/collections/{collection_id}", {
    params: { path: { collection_id: id } },
    body: { visibility },
  });
  if (error) throw new Error(apiErrorMessage(error, "Couldn't change visibility"));
}
export async function fetchMDListFeed(id: string, page = 1, language?: string) {
  const { data, error } = await api.GET("/api/collections/{collection_id}/feed", {
    params: {
      path: { collection_id: id },
      query: { page, pageSize: 30, ...(language ? { language } : {}) },
    },
  });
  if (error || !data) throw new Error(apiErrorMessage(error, "Couldn't load list updates"));
  return data;
}
