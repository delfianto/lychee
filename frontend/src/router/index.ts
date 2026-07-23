import { createRouter, createWebHistory } from "vue-router";

import AppShell from "../layouts/AppShell.vue";
import BrowseView from "../views/BrowseView.vue";
import LibraryHome from "../views/LibraryHome.vue";
import ReaderView from "../views/ReaderView.vue";
import SeriesDetail from "../views/SeriesDetail.vue";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      component: AppShell,
      children: [
        { path: "", name: "home", component: LibraryHome },
        { path: "browse", name: "browse", component: BrowseView },
        { path: "series/:id", name: "series", component: SeriesDetail },
      ],
    },
    // Reader is full-screen — it deliberately sits outside the app shell.
    { path: "/read/:id", name: "reader", component: ReaderView },
  ],
});
