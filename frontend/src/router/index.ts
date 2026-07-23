import { createRouter, createWebHistory } from "vue-router";

import AppShell from "../layouts/AppShell.vue";
import LibraryHome from "../views/LibraryHome.vue";
import SeriesDetail from "../views/SeriesDetail.vue";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      component: AppShell,
      children: [
        { path: "", name: "home", component: LibraryHome },
        { path: "series/:id", name: "series", component: SeriesDetail },
        // Browse (shell child) and the full-screen Reader route are added next.
      ],
    },
  ],
});
