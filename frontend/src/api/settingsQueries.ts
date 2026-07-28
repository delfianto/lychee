// Settings-panel API layer — same job as queries.ts (map responses, turn error
// bodies into thrown Errors) but split out since Settings is a distinct surface
// with its own domain: providers, trackers, libraries, taxonomy, downloads/sync,
// import config, and the server path browser.

import { apiErrorMessage } from "./queries";
import {
  type About,
  type DownloadTask,
  type FsListing,
  type ImportConfig,
  type LibraryRow,
  type PatternPreset,
  type Provider,
  type SyncState,
  type TaxonomyItem,
  type Tracker,
  api,
} from "./client";

// --- providers -------------------------------------------------------------

export async function fetchProviders(): Promise<Provider[]> {
  const { data } = await api.GET("/api/providers");
  return data ?? [];
}

export async function updateProvider(
  id: string,
  patch: {
    enabled?: boolean;
    language?: string;
    autoMatch?: boolean;
    fetchCovers?: boolean;
    dataSaver?: boolean;
  },
): Promise<void> {
  await api.PATCH("/api/providers/{provider_id}", {
    params: { path: { provider_id: id } },
    body: patch,
  });
}

export async function disconnectProvider(id: string): Promise<void> {
  await api.POST("/api/providers/{provider_id}/disconnect", { params: { path: { provider_id: id } } });
}

/** Best-effort, fire-and-forget (matches existing UI: kicked off, not awaited). */
export async function syncProvider(id: string): Promise<void> {
  await api.POST("/api/providers/{provider_id}/sync", { params: { path: { provider_id: id } } });
}

export interface MangaDexConnectData {
  clientId: string;
  clientSecret: string;
  username: string;
  password: string;
}

export async function connectMangaDex(data: MangaDexConnectData): Promise<void> {
  const { error } = await api.POST("/api/providers/{provider_id}/connect", {
    params: { path: { provider_id: "mangadex" } },
    body: data,
  });
  if (error) {
    throw new Error(apiErrorMessage(error, "Connect failed — check credentials & LYCHEE_SECRET_KEY"));
  }
}

// --- trackers ----------------------------------------------------------------

export async function fetchTrackers(): Promise<Tracker[]> {
  const { data } = await api.GET("/api/trackers");
  return data ?? [];
}

export async function disconnectTracker(id: string): Promise<void> {
  await api.DELETE("/api/trackers/{tracker_id}", { params: { path: { tracker_id: id } } });
}

export async function setTrackerSyncOnRead(id: string, syncOnRead: boolean): Promise<void> {
  await api.PATCH("/api/trackers/{tracker_id}", {
    params: { path: { tracker_id: id } },
    body: { syncOnRead },
  });
}

export async function beginTrackerConnect(
  id: string,
  data: { clientId: string; clientSecret: string; redirectUri: string },
): Promise<string> {
  const { data: out, error } = await api.POST("/api/trackers/{tracker_id}/connect", {
    params: { path: { tracker_id: id } },
    body: data,
  });
  if (error || !out) {
    throw new Error(apiErrorMessage(error, "Couldn't start auth — check credentials & LYCHEE_SECRET_KEY"));
  }
  return out.authorizeUrl;
}

export async function completeTrackerConnect(
  id: string,
  data: { code: string; redirectUri: string; state: string },
): Promise<void> {
  const { error } = await api.POST("/api/trackers/{tracker_id}/callback", {
    params: { path: { tracker_id: id } },
    body: data,
  });
  if (error) throw new Error(apiErrorMessage(error, "Authorization failed — is the code correct?"));
}

export async function loginTracker(
  id: string,
  data: { username: string; password: string },
): Promise<void> {
  const { error } = await api.POST("/api/trackers/{tracker_id}/login", {
    params: { path: { tracker_id: id } },
    body: data,
  });
  if (error) {
    throw new Error(apiErrorMessage(error, "Login failed — check credentials & LYCHEE_SECRET_KEY"));
  }
}

// --- libraries -----------------------------------------------------------------

export async function fetchLibraryRows(): Promise<LibraryRow[]> {
  const { data } = await api.GET("/api/libraries");
  return data ?? [];
}

export async function scanAllLibraries(): Promise<void> {
  await api.POST("/api/libraries/scan");
}

export async function scanLibrary(id: string): Promise<void> {
  await api.POST("/api/libraries/{library_id}/scan", { params: { path: { library_id: id } } });
}

export async function deleteLibrary(id: string): Promise<void> {
  await api.DELETE("/api/libraries/{library_id}", { params: { path: { library_id: id } } });
}

export async function addLibrary(data: { name: string; path: string; kind: string }): Promise<void> {
  const { error } = await api.POST("/api/libraries", { body: data });
  if (error) throw new Error(apiErrorMessage(error, "Couldn't add library — check the path exists on the server"));
}

// --- server path browser --------------------------------------------------------

export async function browsePath(path?: string | null): Promise<FsListing> {
  const { data, error } = await api.GET("/api/fs", { params: { query: path ? { path } : {} } });
  if (error || !data) throw new Error("Couldn't read that folder on the server");
  return data;
}

export async function makeDirectory(parent: string, name: string): Promise<FsListing> {
  const { data, error, response } = await api.POST("/api/fs/mkdir", { body: { parent, name } });
  if (error || !data) {
    throw new Error(
      response.status === 409
        ? "A folder with that name already exists"
        : apiErrorMessage(error, "Couldn't create the folder"),
    );
  }
  return await browsePath(parent);
}

// --- taxonomy --------------------------------------------------------------------

export async function fetchTaxonomy(): Promise<TaxonomyItem[]> {
  const { data } = await api.GET("/api/taxonomy", { params: { query: { pageSize: 500 } } });
  return data?.items ?? [];
}

export async function setTaxonomyEnabled(id: string, enabled: boolean): Promise<void> {
  await api.PATCH("/api/taxonomy/{tag_id}", { params: { path: { tag_id: id } }, body: { enabled } });
}

/** Renames a tag's display label — allowed for system rows too (id/group stay fixed). */
export async function renameTaxonomyTag(id: string, name: string): Promise<void> {
  const { error } = await api.PATCH("/api/taxonomy/{tag_id}", {
    params: { path: { tag_id: id } },
    body: { name },
  });
  if (error) throw new Error(apiErrorMessage(error, "Couldn't rename tag"));
}

export async function createTaxonomyTag(name: string, category: string): Promise<TaxonomyItem> {
  const { data, error } = await api.POST("/api/taxonomy", { body: { name, category } });
  if (error || !data) throw new Error(apiErrorMessage(error, "Couldn't add tag"));
  return data;
}

export async function deleteTaxonomyTag(id: string): Promise<void> {
  const { error } = await api.DELETE("/api/taxonomy/{tag_id}", { params: { path: { tag_id: id } } });
  if (error) throw new Error(apiErrorMessage(error, "Couldn't delete tag"));
}

export async function refreshTaxonomy(): Promise<void> {
  const { error } = await api.POST("/api/taxonomy/refresh");
  if (error) throw new Error(apiErrorMessage(error, "Refresh failed"));
}

export async function addTaxonomyAlias(tagId: string, name: string): Promise<void> {
  const { error } = await api.POST("/api/taxonomy/{tag_id}/aliases", {
    params: { path: { tag_id: tagId } },
    body: { name },
  });
  if (error) throw new Error(apiErrorMessage(error, "Couldn't add alias"));
}

export async function deleteTaxonomyAlias(tagId: string, aliasId: string): Promise<void> {
  const { error } = await api.DELETE("/api/taxonomy/{tag_id}/aliases/{alias_id}", {
    params: { path: { tag_id: tagId, alias_id: aliasId } },
  });
  if (error) throw new Error(apiErrorMessage(error, "Couldn't remove alias"));
}

// --- downloads + sync --------------------------------------------------------------

export async function fetchDownloadTasks(): Promise<DownloadTask[]> {
  const { data } = await api.GET("/api/downloads");
  return data ?? [];
}

export async function fetchSyncState(): Promise<SyncState | null> {
  const { data } = await api.GET("/api/sync");
  return data ?? null;
}

/** Runs on the queue; UI state reloads on the sync task's `done` SSE event. */
export async function runSync(): Promise<void> {
  await api.POST("/api/sync");
}

export async function retryDownload(id: string): Promise<void> {
  await api.POST("/api/downloads/{task_id}/retry", { params: { path: { task_id: id } } });
}

export async function pauseDownload(id: string): Promise<DownloadTask[] | null> {
  const { data } = await api.POST("/api/downloads/{task_id}/pause", { params: { path: { task_id: id } } });
  return data ?? null;
}

export async function resumeDownload(id: string): Promise<DownloadTask[] | null> {
  const { data } = await api.POST("/api/downloads/{task_id}/resume", {
    params: { path: { task_id: id } },
  });
  return data ?? null;
}

export async function deleteDownloadTask(id: string): Promise<void> {
  await api.DELETE("/api/downloads/{task_id}", { params: { path: { task_id: id } } });
}

export async function clearCompletedDownloads(): Promise<void> {
  await api.POST("/api/downloads/clear-completed");
}

export interface BulkDownloadResult {
  /** Present when the bulk action returned the refreshed list directly (200). */
  rows: DownloadTask[] | null;
}

export async function bulkDownloadAction(
  action: "pause-all" | "cancel-all" | "resume-all",
): Promise<BulkDownloadResult> {
  const { data, error, response } = await api.POST("/api/downloads", { body: { action } });
  if (error) throw new Error(apiErrorMessage(error, "Couldn't update downloads"));
  return { rows: response.status === 200 && Array.isArray(data) ? (data as DownloadTask[]) : null };
}

// --- local import ------------------------------------------------------------------

export async function fetchImportConfig(): Promise<ImportConfig | null> {
  const { data } = await api.GET("/api/import/config");
  return data ?? null;
}

export async function updateImportConfig(patch: {
  enabled?: boolean;
  quality?: number;
  filenamePattern?: string;
  patternPresets?: PatternPreset[];
}): Promise<void> {
  await api.PATCH("/api/import/config", { body: patch });
}

export async function startImport(path: string, kind: string): Promise<void> {
  const { error } = await api.POST("/api/import", { body: { path, kind } });
  if (error) {
    throw new Error(apiErrorMessage(error, "Import failed — check the path and that import is enabled"));
  }
}

/** Raw multipart upload — not the JSON openapi-fetch client. */
export async function uploadImportFiles(files: File[], kind: string): Promise<void> {
  const form = new FormData();
  for (const file of files) form.append("files", file); // one batch → one series
  form.append("kind", kind);
  const resp = await fetch("/api/import/upload", { method: "POST", body: form });
  if (!resp.ok) {
    throw new Error("Upload failed — check the file type/size and that import is enabled");
  }
}

// --- about -------------------------------------------------------------------------

export async function fetchAbout(): Promise<About | null> {
  const { data } = await api.GET("/api/about");
  return data ?? null;
}
