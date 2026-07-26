// Typed API client (openapi-fetch over the generated schema). Requests are
// same-origin; the Vite dev server proxies /api → the FastAPI backend.
//
// Regenerate types after changing the backend API:
//   (backend) uv run python scripts/dump_openapi.py
//   (frontend) bun run api:gen

import createClient from "openapi-fetch";
import type { components, paths } from "./schema";

export const api = createClient<paths>();

type Schemas = components["schemas"];

export type Series = Schemas["SeriesOut"];
export type SeriesUpdate = Schemas["SeriesUpdate"];
export type Tag = Schemas["TagOut"];
export type Chapter = Schemas["ChapterOut"];
export type ChapterDetail = Schemas["ChapterDetailOut"];
export type VolumeGroup = Schemas["VolumeGroupOut"];
export type RecentUpdate = Schemas["RecentUpdateOut"];
export type Dashboard = Schemas["DashboardOut"];
export type SeriesArt = Schemas["SeriesArtOut"];
export type SeriesPage = Schemas["Page_SeriesOut_"];
export type UpdatePage = Schemas["Page_RecentUpdateOut_"];
export type ImagePage = Schemas["Page_str_"];
