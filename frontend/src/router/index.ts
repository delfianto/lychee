import { createRouter, createWebHistory } from "vue-router";

import AppShell from "../layouts/AppShell.vue";
import AddedView from "../views/AddedView.vue";
import LibraryHome from "../views/LibraryHome.vue";
import LibraryView from "../views/LibraryView.vue";
import ReaderView from "../views/ReaderView.vue";
import SeriesDetail from "../views/SeriesDetail.vue";
import SettingsView from "../views/SettingsView.vue";
import UpdatesView from "../views/UpdatesView.vue";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      component: AppShell,
      children: [
        { path: "", name: "home", component: LibraryHome },
        { path: "series/:id", name: "series", component: SeriesDetail },
        { path: "settings", name: "settings", component: SettingsView },
        { path: "favorites", name: "favorites", component: LibraryView, props: { libraryKey: "favorites" } },
        { path: "manga", name: "manga", component: LibraryView, props: { libraryKey: "manga" } },
        { path: "comics", name: "comics", component: LibraryView, props: { libraryKey: "comics" } },
        { path: "updates", name: "updates", component: UpdatesView },
        { path: "added", name: "added", component: AddedView },
      ],
    },
    // Reader is full-screen — it deliberately sits outside the app shell.
    { path: "/read/:id", name: "reader", component: ReaderView },
  ],
});
