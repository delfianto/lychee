# User interface

A tour of Lychee's library, reader, galleries, and settings. These are real browser
captures of the local MSW harness, using fictional titles and generated artwork.
Account names, server statistics, chapter pages, and download states are demo data.
They illustrate the interface rather than a live media collection.

[Back to the project README](../README.md) · [Capture notes](assets/README.md)

To explore the same demo locally:

```sh
just fe-install
just fe-mock
```

Open **http://localhost:5173**. A full reload restores the demo data. For a real
library, use the backend and frontend startup instructions in the
[main README](../README.md#run-locally).

## Home

The dashboard combines library totals, a continue-reading carousel, recent
chapter updates, and recently added series. The navigation bar provides search,
a random-series shortcut, background task progress, theme switching, and settings.

![Home dashboard](assets/home.png)

## Browse and filter

The manga and comics libraries share shelf tabs, sorting, search, and density
controls. Favorites and Reading provide focused views of the same catalog.

![Manga cover grid](assets/library-grid.png)

<details>
<summary>List and compact layouts</summary>

List mode emphasizes descriptions, creators, ratings, and tags. Compact mode
fits more series into the same space.

![Library list layout](assets/library-list.png)

![Library compact layout](assets/library-compact.png)

</details>

**Filters** combines tags, content ratings, demographics, publication status, and
read state. Tag buttons cycle through neutral, included, and excluded. Choose
AND/OR matching, save a named preset, or remove individual active-filter chips.

![Advanced filters and active filter chips](assets/library-filters.png)

<details>
<summary>Comics, favorites, Reading, and recently added</summary>

![Comic library](assets/comics.png)

![Favorites](assets/favorites.png)

![Reading shelf](assets/reading.png)

![Recently added](assets/recently-added.png)

</details>

## Search and chapter feeds

The navigation search opens a library-wide search page. Recently updated and
unread-chapter feeds provide chapter-focused browsing, with thumbnail and list
layouts.

![Library-wide search results](assets/search.png)

<details>
<summary>Recent and unread chapter feeds</summary>

![Recent chapter updates](assets/updates.png)

![Unread chapters](assets/unread.png)

</details>

## Series details

A series page brings together its synopsis, creators, tags, community score,
personal rating, reading shelf, favorites, and reading-list membership. The
chapter table distinguishes local chapters from remote chapters available to
download, with language and ordering controls.

![Series details and chapter list](assets/series-detail.png)

<details>
<summary>Related series, artwork, editing, and metadata matching</summary>

The chapter area also has Related and Art tabs. **Edit** changes local metadata;
the metadata-source menu searches MangaDex for a match or refreshes an existing
match.

![Related series tab](assets/series-related.png)

![Series artwork tab](assets/series-art.png)

![Edit series metadata](assets/edit-metadata.png)

![MangaDex match search](assets/match-series.png)

</details>

## Reader

The reader fills the screen and keeps chapter navigation, page controls, and a
scrubber close to the content. Arrow keys follow the selected reading direction.
Use the settings button for page layout, fit, background, and direction; Escape
closes settings before leaving the reader.

![Full-screen reader](assets/reader.png)

![Reader settings for layout, direction, fit, and background](assets/reader-settings.png)

Single, double, and long-strip modes serve different page layouts. Paged reading
writes progress as pages turn. The pages shown here are generated placeholders,
not scans of a real book.

## Reading lists

Lists group series into custom collections. Filter lists by manga, comics, or
galleries, or show them all. Open a list to rename it, remove individual works,
or delete the collection.

![Reading lists across media kinds](assets/lists.png)

![Contents of a reading list](assets/list-detail.png)

## Galleries

The gallery browser uses large cover cards, with artist and source filters.
Gallery details show creators/models, source, characters, tags, and the media
grid. Open an item in the full-screen lightbox to move between images and GIFs.
Supported video formats play through the gallery player; playback depends on
the browser's codec support.

![Gallery browser](assets/gallery.png)

<details>
<summary>Gallery details and lightbox</summary>

![Gallery metadata and image grid](assets/gallery-detail.png)

![Full-screen gallery image](assets/gallery-lightbox.png)

The harness generates still placeholders for gallery media. A video badge in the
demo does not establish playback of a real video file.

</details>

## Settings

### General

General contains metadata-provider options, provider/tracker account connections,
shared appearance preferences, reader defaults, and gallery playback preferences.
Choose a theme, switch between its light and dark variants, or change the root
font size to scale the interface.

![General settings, accounts, appearance, and theme choices](assets/settings-general.png)

### Libraries and local import

Register a folder using its path on the server, scan one root or all roots, and
follow task completion in the navigation bar. Local import supports server paths
and browser uploads, image-quality settings, filename patterns, and saved presets.
The storage browser is scoped to the configured storage root; paths can also be
typed directly.

![Library roots and local import settings](assets/settings-libraries.png)

<details>
<summary>Add a library and browse server storage</summary>

![Add-library dialog](assets/add-library.png)

![Server-side storage browser](assets/path-browser.png)

</details>

### Content

Manage the taxonomy in one searchable, paginated table. Enable or disable tags,
rename display labels, maintain aliases, and refresh the provider vocabulary.
System tags retain their identities and deletion restrictions.

![Content taxonomy and tag aliases](assets/settings-content.png)

### Downloads

The queue distinguishes fetching, encoding, queued, paused, completed, and failed
work. Pause/resume individual entries or the queue, retry failures, clear completed
items, and confirm cancellation of active downloads. The sync card starts a
MangaDex check and shows its latest result.

![Download queue with mixed states and sync controls](assets/settings-downloads.png)

### About

About shows version, platform, database, uptime, and library totals. All values in
this capture come from demo fixtures.

![About and library summary](assets/settings-about.png)

## Themes and small screens

The same interface adapts to narrower screens, including a navigation drawer and
a full-screen reader. Appearance preferences are shared across the app.

![Dashboard in the light theme](assets/home-light.png)

<details>
<summary>Mobile layouts</summary>

<img src="assets/mobile-home.png" alt="Home dashboard on a 390-pixel-wide viewport" width="390">

<img src="assets/mobile-navigation.png" alt="Mobile navigation drawer" width="390">

<img src="assets/mobile-library.png" alt="Manga library on a narrow viewport" width="390">

<img src="assets/mobile-reader.png" alt="Reader on a narrow viewport" width="390">

</details>
