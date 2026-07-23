import { createRouter, createWebHistory } from "vue-router";

import AppShell from "../layouts/AppShell.vue";
import LibraryHome from "../views/LibraryHome.vue";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      component: AppShell,
      children: [{ path: "", name: "home", component: LibraryHome }],
      // Series Detail, Browse (shell children) and the full-screen Reader route
      // are added as those views are translated.
    },
  ],
});
