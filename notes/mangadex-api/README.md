# MangaDex API — Research Note

> Why this is here: MangaDex exposes a **free, public, richly-curated dataset** that is the natural
> foundation for lychee's **metadata fetching** and (optionally) **chapter downloading**. Its tag +
> content-rating taxonomy is the one we already mirrored in [decision 10](../decisions/10-tagging-content-rating.md).
> Researched against the live docs, 2026-07. Sources listed at the bottom.

## Quick facts

| | |
|---|---|
| Base URL | `https://api.mangadex.org` (dev: `api.mangadex.dev`) |
| Auth | OAuth2 **Resource-Owner-Password** grant via a **personal client**; **most read endpoints are public** (no auth) |
| Format | JSON, JSON:API-ish (`data` + `relationships[]`, reference-expansion via `includes[]`) |
| Global rate limit | **~5 req/s per IP**; `429` → back off, persisting → `403` DDoS ban |
| Pagination caps | `limit` ≤ **100** (500 for some feeds); `offset + limit` ≤ **10,000** |
| Cover images | `uploads.mangadex.org/covers/{mangaId}/{fileName}` (+ `.256.jpg` / `.512.jpg` thumbs) |
| Page images | via **MangaDex@Home**: `GET /at-home/server/{chapterId}` → temporary `baseUrl` |
| Cost / licence | free & public, but **3 rules**: credit MangaDex, credit scanlation groups + honor takedowns, **no monetization** |

**TL;DR.** Metadata (manga, tags, ratings, covers, chapter lists) is free and encouraged to consume — it's a great backbone. **Chapter image downloading is also supported** (the @Home endpoint), but it's the sensitive part: governed by rate limits (40 req/min), a mandatory network-health report, and an acceptable-use policy aimed squarely at *personal* use, not public re-hosting/aggregation. Self-hosted personal downloading (what Mihon and Mango's plugins do) is legitimate; lychee must bake the ToS constraints into the implementation.

---

## 1. Access & authentication

- **Public reads:** search, manga, tag list, cover, chapter feed, and `/at-home/server` are usable **without authentication** — enough for all metadata + cover + (personal) downloading. This is the mode lychee will use by default.
- **Personal client (only if we need user-scoped actions):** register at `mangadex.org/settings` → `client_id` (`personal-client-…`) + `client_secret`. OAuth2 **password grant** to `https://auth.mangadex.org/realms/mangadex/protocol/openid-connect/token`; **access token ~15 min**, refresh token to renew. Needed only for account actions (follows, custom lists, ratings, uploads) — **not** for metadata/cover/page reads.
- **Auth headers must only go to `{api,auth}.mangadex.org`** — never to `uploads.mangadex.org` or `*.mangadex.network` (image domains). Important when we build the download client.

## 2. Rate limits & acceptable use (the constraints that shape the design)

- **Global:** ~5 req/s per IP (a floor, not exact).
- **Per-endpoint** (the ones we'll hit):
  - `GET /at-home/server/{id}` → **40 / min** (the download bottleneck).
  - `POST /auth/login` → 30 / 60 min; `POST /auth/refresh` → 60 / 60 min.
  - `GET /manga/random` 60/min; `POST /chapter/{id}/read` 300/10min; writes/uploads have their own low caps.
- **Discipline:** send a **legitimate `User-Agent`**; back off on `429` (persisting escalates to a `403` IP ban); don't issue redundant bulk requests where one call suffices; transparent proxies only.
- **Acceptable-use / ToS:** the API is free & public with three hard rules — (1) **credit MangaDex**; (2) if you offer reading, **credit scanlation groups and honor their removal/takedown requests**; (3) **no monetization** (no ads/paid tiers; donations are OK). Pornographic content is hidden unless explicitly requested.
- **Ethics for downloading:** the policy exists to stop parasitic aggregators; a personal self-hosted server that rate-limits, reports to @Home, credits groups, and honors takedowns is within the spirit. lychee should treat these as implementation requirements, not optional.

## 3. Data model

JSON:API style: every object has `id`, `type`, `attributes`, and `relationships[]` (each a `{type, id}`); `includes[]=cover_art&includes[]=author` **expands** related objects inline to avoid N+1 calls.

- **Manga** — `title` (localized map), `altTitles[]`, `description` (localized), `links` (al=AniList, mal=MyAnimeList, mu=MangaUpdates, …), `originalLanguage`, `lastVolume`, `lastChapter`, `publicationDemographic`, `status`, `year`, `contentRating`, `tags[]`, `state`, `version`. Relationships: `author`, `artist`, `cover_art`.
- **Chapter** — `volume`, `chapter` (decimal string), `title`, `translatedLanguage`, `pages` (count), `externalUrl` (set for official/off-site chapters — **not** downloadable via @Home), `publishAt`, `readableAt`. Relationships: `scanlation_group`, `manga`, `user`.
- **Cover** — `fileName`, `volume`, `locale`.
- **Author/Artist**, **ScanlationGroup**, **CustomList**, **User**.

## 4. Tag & content-rating taxonomy → seeds decision 10

This is the payoff of mirroring MangaDex in [10](../decisions/10-tagging-content-rating.md):

- **`GET /manga/tag`** returns the **entire tag vocabulary** — each tag = a stable **UUID** + localized `name` + `group` ∈ {`content`, `format`, `genre`, `theme`}. → **seed lychee's `tag` / `tag_group` fixtures directly from this**, using the MangaDex tag id/slug as our stable `tag.key` so provider tags map 1:1 with zero fuzzy matching.
- **`contentRating`** enum = `safe · suggestive · erotica · pornographic` → **identical** to our `content_rating` fixtures (levels 0–3).
- **`publicationDemographic`** = `shounen · shoujo · josei · seinen · none` → our `demographic` fixtures.
- **`status`** = `ongoing · completed · hiatus · cancelled` → our series status.

So 10's taxonomy isn't just "inspired by" MangaDex — it's **wire-compatible**, which makes the metadata provider trivial.

## 5. Metadata fetching flow (feeds the metadata-provider plugin)

1. **Match** a local series → a MangaDex manga: `GET /manga?title=<name>&includes[]=cover_art&includes[]=author&includes[]=artist` (optionally filter `year`, `originalLanguage`); rank candidates by title/altTitle similarity + year. Let the user confirm/override for low-confidence matches.
2. **Persist the external id** (`mangadex:manga:<uuid>`) on the series so re-sync is exact and idempotent (new mapping — see below).
3. **Map fields** onto our schema, applying only to **unlocked** fields ([05](../decisions/05-domain-model.md) `locked_fields`):

| MangaDex | lychee |
|---|---|
| `title` / `altTitles` | `series.title` / alt titles |
| `description` | `series.summary` |
| `originalLanguage` | `series.language` |
| `status` | `series.status` |
| `year` | series year |
| `contentRating` | `series.content_rating_id` (+ denormalized level) |
| `publicationDemographic` | `series.demographic_id` |
| `tags[]` (group+id) | `series_tag` (seeded vocabulary, id-matched) |
| `links` (al/mal/mu) | external links (future cross-linking / trackers) |
| `author` / `artist` (includes) | `book_author` / series authors (name + role) |
| `cover_art.fileName` | download → series cover ([09](../decisions/09-image-serving.md)) |

## 6. Cover art

From the `cover_art` relationship's `fileName`: `https://uploads.mangadex.org/covers/{mangaId}/{fileName}` — full-size, or append `.512.jpg` / `.256.jpg` for thumbnails. No auth header. Fits straight into 09's cover pipeline (store as a `sidecar`/`provider` cover source so it doesn't get clobbered by generated thumbnails).

## 7. Chapter listing & downloading (@Home)

- **List:** `GET /manga/{id}/feed` (or `GET /chapter?manga=…`) with `translatedLanguage[]` (pick a language), `order[chapter]=asc`, `includes[]=scanlation_group`. Feed `limit` up to 500. Gives `volume`/`chapter`/`pages`/`externalUrl` per chapter.
- **Download a chapter's pages:**
  1. `GET /at-home/server/{chapterId}` → `{ baseUrl, chapter: { hash, data[], dataSaver[] } }`. `baseUrl` is **temporary (~15 min) and geo-optimized — never cache/hardcode it**.
  2. Build each page URL: `{baseUrl}/{data|data-saver}/{hash}/{filename}` (`data` = full quality, `data-saver` = compressed).
  3. **Report every fetch** to `POST https://api.mangadex.network/report` (`url`, `success`, `cached`, `bytes`, `duration`) — required for network health (skip only for `mangadex.org`-hosted URLs).
  4. Refresh `baseUrl` on `403`/after ~15 min.
- **Skip `externalUrl` chapters** (official publisher links) — not served via @Home.
- **Limits:** 40 `/at-home/server` calls/min; no auth headers to image/network domains; obey the global 5 req/s.

## 8. Relevance to lychee — concrete integration plan

- **Seed [10](../decisions/10-tagging-content-rating.md) fixtures from `/manga/tag`** (pin a snapshot in-repo; refresh via an admin action). Ratings/demographics/status enums copied verbatim.
- **Metadata provider = the first plugin** behind the provider interface flagged in [10](../decisions/10-tagging-content-rating.md)/[05](../05-metadata-tagging.md): `MangaDexProvider.match()` + `.fetch() -> patch`, merged onto unlocked fields, run as a task ([08](../decisions/08-task-runner.md)).
- **New mapping table** for external ids — `external_link(entity_type, entity_id, provider, external_id, url)` — so a series/book can be re-synced and downloads deduped against `mangadex:manga:<uuid>` / `mangadex:chapter:<uuid>`.
- **Downloader (optional feature)** ties into the task queue ([08](../decisions/08-task-runner.md)): a `download_chapter` task type, gated by a **per-provider rate limiter** (5 req/s global + 40/min @Home), that fetches pages, writes a **CBZ + `ComicInfo.xml`** (KamiYomu's pattern — populated from the MangaDex metadata + scanlation-group credit) into a library folder so the **normal scan** ([07](../decisions/07-scan-pipeline.md)) ingests it. This reuses the whole existing pipeline instead of a separate ingest path.
- **ToS compliance is non-negotiable in code:** real `User-Agent`, back-off on 429, @Home reporting, credit scanlation groups in the CBZ/UI, honor removal requests, no ads/paywall. Note this is why the download client must be its own rate-limited, well-behaved component.
- **This warrants its own decision** → now [decision 13](../decisions/13-metadata-providers.md) (provider interface, external-id mapping, rate limiting, CBZ+ComicInfo output, ToS guards) + [14](../decisions/14-metadata-mapping.md) (field mapping & lock-merge).

## Caveats & open questions

- **Matching accuracy** — title matching is fuzzy; needs a confidence threshold + manual confirm/override (don't auto-apply low-confidence matches).
- **Language selection** — a manga has chapters in many languages; the downloader/lister needs a per-library or per-series preferred `translatedLanguage`.
- **Scanlation duplication** — multiple groups scanlate the same chapter; need a policy (prefer a group, or let the user pick).
- **Licensed/removed titles** — some manga have no readable chapters on MangaDex (licensing); metadata still fetchable, chapters not.
- **Tag snapshot drift** — MangaDex occasionally adds tags; our seed is a snapshot, refreshable via `/manga/tag`.

## Sources

- [Authentication](https://api.mangadex.org/docs/02-authentication/) · [Personal clients](https://api.mangadex.org/docs/02-authentication/personal-clients/)
- [Limitations & Requirements (rate limits, acceptable use)](https://api.mangadex.org/docs/2-limitations/)
- [Manga](https://api.mangadex.org/docs/03-manga/) · [Searching for a manga](https://api.mangadex.org/docs/03-manga/search/)
- [Find a Manga's chapters (feed)](https://api.mangadex.org/docs/04-chapter/feed/) · [Retrieving a chapter's images (@Home)](https://api.mangadex.org/docs/04-chapter/retrieving-chapter/)
- [API reference (Redoc)](https://api.mangadex.org/docs/redoc.html) · [Swagger](https://api.mangadex.org/docs/swagger.html)
