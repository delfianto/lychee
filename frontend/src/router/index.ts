import { createRouter, createWebHistory } from "vue-router";
import { createBrowseScroll } from "../lib/browseScroll";

import AppShell from "../layouts/AppShell.vue";
import AddedView from "../views/AddedView.vue";
import ChapterFeedView from "../views/ChapterFeedView.vue";
import GalleryDetail from "../views/GalleryDetail.vue";
import GalleryView from "../views/GalleryView.vue";
import LibraryHome from "../views/LibraryHome.vue";
import LibraryView from "../views/LibraryView.vue";
import ListDetailView from "../views/ListDetailView.vue";
import ListsView from "../views/ListsView.vue";
import NotFoundView from "../views/NotFoundView.vue";
import ReaderView from "../views/ReaderView.vue";
import SearchView from "../views/SearchView.vue";
import SeriesDetail from "../views/SeriesDetail.vue";
import SettingsView from "../views/SettingsView.vue";

const browsing = createBrowseScroll();

export const router = createRouter({
  history: createWebHistory(),
  scrollBehavior(to, _from, savedPosition) {
    if (to.name === "reader") return { left: 0, top: 0 };
    return browsing.restore(to.fullPath, savedPosition, to.meta.browse === true);
  },
  routes: [
    {
      path: "/",
      component: AppShell,
      children: [
        { path: "", name: "home", meta: { browse: true }, component: LibraryHome },
        { path: "series/:id", name: "series", component: SeriesDetail },
        { path: "settings", name: "settings", component: SettingsView },
        {
          path: "favorites",
          name: "favorites",
          meta: { browse: true },
          component: LibraryView,
          props: { libraryKey: "favorites" },
        },
        {
          path: "reading",
          name: "reading",
          meta: { browse: true },
          component: LibraryView,
          props: { libraryKey: "reading" },
        },
        {
          path: "manga",
          name: "manga",
          meta: { browse: true },
          component: LibraryView,
          props: { libraryKey: "manga" },
        },
        {
          path: "comics",
          name: "comics",
          meta: { browse: true },
          component: LibraryView,
          props: { libraryKey: "comics" },
        },
        { path: "gallery", name: "gallery", meta: { browse: true }, component: GalleryView },
        { path: "gallery/:id", name: "gallery-detail", component: GalleryDetail },
        {
          path: "updates",
          name: "updates",
          meta: { browse: true },
          component: ChapterFeedView,
          props: { unreadOnly: false },
        },
        {
          path: "unread",
          name: "unread",
          meta: { browse: true },
          component: ChapterFeedView,
          props: { unreadOnly: true },
        },
        { path: "added", name: "added", meta: { browse: true }, component: AddedView },
        { path: "lists", name: "lists", meta: { browse: true }, component: ListsView },
        {
          path: "lists/:id",
          name: "list-detail",
          meta: { browse: true },
          component: ListDetailView,
        },
        { path: "search", name: "search", meta: { browse: true }, component: SearchView },
        { path: ":pathMatch(.*)*", name: "not-found", component: NotFoundView },
      ],
    },
    // Reader is full-screen — it deliberately sits outside the app shell.
    { path: "/read/:id", name: "reader", component: ReaderView },
  ],
});

router.beforeEach((_to, from) => {
  browsing.cancel();
  if (from.meta.browse) browsing.remember(from.fullPath);
});
