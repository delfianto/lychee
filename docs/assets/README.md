# Screenshot assets

These PNGs are browser captures of Lychee's local MSW harness, taken on
2026-10-23. They appear in the [main README](../../README.md) and the
[user-interface tour](../README.md).

## Source and scope

- UI: the Vue app in [`frontend/src/`](../../frontend/src/).
- Data and generated artwork: [`frontend/src/mocks/`](../../frontend/src/mocks/).
- Browser: Chromium, driven with Playwright.
- Desktop viewport: **1440 × 1000**, device scale factor 1.
- Mobile viewport: **390 × 844**, device scale factor 1.
- Locale/time zone: **en-US / UTC**. Font size: **16 px**.
- Theme: default dark, except `home-light.png`.
- Settings overview and mobile home use full-page captures; most other images
  show one viewport. Exact flags, routes, browser version, and capture time are
  recorded in [`screenshots.json`](screenshots.json).

Titles are fictional, artwork/pages are seeded SVG placeholders, and server
statistics, account names, queue entries, and task results are fixtures. No live
library, provider credentials, or third-party image host was used. The captures
show the app as rendered; the UI and images were not repainted or composited.

## Refreshing the screenshots

1. Run `just fe-install`, then `just fe-mock` from the repository root.
2. Open `http://localhost:5173` in Chromium. Use a clean browser context, the
   viewport sizes above, the default theme, and a 16 px font size.
3. Visit the routes below and apply the recorded UI state. A full reload resets
   the MSW fixtures; use the UI controls to select settings panels and open
   dialogs. Reader screenshots use a locally available chapter from the series
   chapter response.
4. Wait for data, covers, and page images to load. For full-page captures, load
   lazy images below the fold before capturing. The SSE stream stays open, so
   waiting for complete network idleness is unsuitable.
5. Save PNGs through browser automation or Chromium's screenshot tools, keeping
   the filenames below. Capture the rendered UI without modifying its content.
6. Update `screenshots.json`, check the Markdown links, and inspect both the
   desktop and mobile images before committing.

The capture pass reported **zero browser page errors**. A capture tool or
Playwright installation is needed only to refresh images; it is not required to
run the MSW demo.

## Capture index

| Screenshot                                       | Route                                         | State                                                                  |
| ------------------------------------------------ | --------------------------------------------- | ---------------------------------------------------------------------- |
| [home.png](home.png)                             | `/`                                           | Default screen state for the recorded route.                           |
| [library-grid.png](library-grid.png)             | `/manga?view=gallery`                         | Default screen state for the recorded route.                           |
| [library-filters.png](library-filters.png)       | `/manga?view=gallery`                         | Filters open; Action included; OR tag matching selected.               |
| [library-list.png](library-list.png)             | `/manga?view=list`                            | Default screen state for the recorded route.                           |
| [library-compact.png](library-compact.png)       | `/manga?view=compact`                         | Default screen state for the recorded route.                           |
| [comics.png](comics.png)                         | `/comics?view=gallery`                        | Default screen state for the recorded route.                           |
| [favorites.png](favorites.png)                   | `/favorites?view=gallery`                     | Default screen state for the recorded route.                           |
| [reading.png](reading.png)                       | `/reading?view=list`                          | Default screen state for the recorded route.                           |
| [recently-added.png](recently-added.png)         | `/added`                                      | Gallery density selected with the toolbar control.                     |
| [updates.png](updates.png)                       | `/updates`                                    | Default screen state for the recorded route.                           |
| [unread.png](unread.png)                         | `/unread`                                     | Default screen state for the recorded route.                           |
| [search.png](search.png)                         | `/search?q=night`                             | Default screen state for the recorded route.                           |
| [lists.png](lists.png)                           | `/lists`                                      | All media-kind tabs selected via the All tab.                          |
| [list-detail.png](list-detail.png)               | `/lists/list-currently-reading`               | Default screen state for the recorded route.                           |
| [series-detail.png](series-detail.png)           | `/series/nightfall-requiem`                   | Default screen state for the recorded route.                           |
| [series-related.png](series-related.png)         | `/series/nightfall-requiem`                   | Related tab selected in the chapter area.                              |
| [series-art.png](series-art.png)                 | `/series/nightfall-requiem`                   | Art tab selected in the chapter area.                                  |
| [edit-metadata.png](edit-metadata.png)           | `/series/nightfall-requiem`                   | Series Edit dialog open; no edits submitted.                           |
| [match-series.png](match-series.png)             | `/series/nightfall-requiem`                   | Metadata source menu → Match on MangaDex; initial title search loaded. |
| [reader.png](reader.png)                         | `/read/nightfall-requiem-c142`                | Default screen state for the recorded route.                           |
| [reader-settings.png](reader-settings.png)       | `/read/nightfall-requiem-c142`                | Reader settings panel open.                                            |
| [gallery.png](gallery.png)                       | `/gallery`                                    | Default screen state for the recorded route.                           |
| [gallery-detail.png](gallery-detail.png)         | `/gallery/moonfall-tactics-official-artworks` | Default screen state for the recorded route.                           |
| [gallery-lightbox.png](gallery-lightbox.png)     | `/gallery/moonfall-tactics-official-artworks` | First still image open in the gallery lightbox.                        |
| [settings-general.png](settings-general.png)     | `/settings`                                   | General tab; full-page capture includes appearance and theme choices.  |
| [settings-libraries.png](settings-libraries.png) | `/settings`                                   | Libraries tab; full-page capture includes Local import.                |
| [add-library.png](add-library.png)               | `/settings`                                   | Libraries tab → Add library; empty registration form.                  |
| [path-browser.png](path-browser.png)             | `/settings`                                   | Libraries → Add library → Browse; storage root listing.                |
| [settings-content.png](settings-content.png)     | `/settings`                                   | Content tab; first taxonomy page.                                      |
| [settings-downloads.png](settings-downloads.png) | `/settings`                                   | Downloads tab; seeded queue states and sync summary.                   |
| [settings-about.png](settings-about.png)         | `/settings`                                   | About tab; all version/platform/statistic values are fixtures.         |
| [mobile-home.png](mobile-home.png)               | `/`                                           | Default screen state for the recorded route.                           |
| [mobile-navigation.png](mobile-navigation.png)   | `/`                                           | Home route with mobile navigation drawer open.                         |
| [mobile-library.png](mobile-library.png)         | `/manga?view=gallery`                         | Default screen state for the recorded route.                           |
| [mobile-reader.png](mobile-reader.png)           | `/read/nightfall-requiem-c142`                | Default screen state for the recorded route.                           |
| [home-light.png](home-light.png)                 | `/`                                           | Home route after switching from the dark theme to light.               |
