<script setup lang="ts">
import {
  Book,
  BookOpen,
  Cherry,
  ChevronsLeft,
  ChevronsRight,
  Compass,
  Dices,
  Heart,
  House,
  Images,
  Library,
  List,
  Menu,
  Search,
  Settings,
} from "lucide-vue-next";
import { type Component, ref } from "vue";
import { RouterLink, RouterView } from "vue-router";

// Primary nav (only routed items link; the rest are placeholders until built).
const primary: { label: string; icon: Component; to?: string }[] = [
  { label: "Home", icon: House, to: "/" },
  { label: "Favorites", icon: Heart },
  { label: "Browse", icon: Compass, to: "/browse" },
  { label: "Search", icon: Search },
  { label: "Reading", icon: BookOpen },
  { label: "Random", icon: Dices },
];

const libraries: { label: string; icon: Component; count: number }[] = [
  { label: "Lists", icon: List, count: 4 },
  { label: "Manga", icon: Book, count: 128 },
  { label: "Comics", icon: Images, count: 42 },
  { label: "Books", icon: Library, count: 17 },
];

const collapsed = ref(false); // desktop: collapse to an icon rail
const mobileOpen = ref(false); // mobile: off-canvas drawer

function closeMobile(): void {
  mobileOpen.value = false;
}
</script>

<template>
  <div class="drawer min-h-dvh lg:drawer-open">
    <input id="app-drawer" v-model="mobileOpen" type="checkbox" class="drawer-toggle" />

    <!-- Content column -->
    <div class="drawer-content flex min-h-dvh flex-col bg-base-200">
      <header class="navbar sticky top-0 z-10 border-b border-base-300 bg-base-100/90 backdrop-blur">
        <div class="navbar-start gap-1">
          <label for="app-drawer" class="btn btn-square btn-ghost btn-sm lg:hidden" aria-label="Menu">
            <Menu class="size-5" />
          </label>
          <button
            class="btn btn-square btn-ghost btn-sm hidden lg:inline-flex"
            aria-label="Toggle sidebar"
            @click="collapsed = !collapsed"
          >
            <ChevronsRight v-if="collapsed" class="size-5" />
            <ChevronsLeft v-else class="size-5" />
          </button>
          <label class="input input-bordered input-sm ml-1 hidden items-center gap-2 sm:flex">
            <Search class="size-4 opacity-60" />
            <input type="search" class="grow" placeholder="Search…" />
          </label>
        </div>
        <div class="navbar-end gap-1">
          <button class="btn btn-circle btn-ghost btn-sm" aria-label="Random"><Dices class="size-5" /></button>
          <RouterLink to="/settings" class="btn btn-circle btn-ghost btn-sm" aria-label="Settings">
            <Settings class="size-5" />
          </RouterLink>
          <div class="avatar avatar-placeholder">
            <div class="w-8 rounded-full bg-neutral text-neutral-content"><span class="text-xs">U</span></div>
          </div>
        </div>
      </header>

      <main class="grow overflow-x-hidden">
        <RouterView />
      </main>
    </div>

    <!-- Sidebar -->
    <div class="drawer-side z-20">
      <label for="app-drawer" class="drawer-overlay" aria-label="Close menu"></label>
      <aside
        class="flex min-h-dvh flex-col border-r border-base-300 bg-base-100 transition-all duration-200"
        :class="collapsed ? 'w-16' : 'w-64'"
      >
        <div class="flex h-14 items-center gap-2 px-4 text-xl font-bold">
          <Cherry class="size-6 shrink-0 text-primary" /><span v-show="!collapsed">lychee</span>
        </div>

        <ul class="menu w-full gap-0.5 px-2">
          <li v-for="item in primary" :key="item.label">
            <RouterLink
              v-if="item.to"
              :to="item.to!"
              active-class="menu-active"
              :exact-active-class="item.to === '/' ? 'menu-active' : undefined"
              :class="{ 'justify-center px-0': collapsed }"
              @click="closeMobile"
            >
              <component :is="item.icon" class="size-5 shrink-0" />
              <span v-show="!collapsed">{{ item.label }}</span>
            </RouterLink>
            <a v-else class="opacity-80" :class="{ 'justify-center px-0': collapsed }">
              <component :is="item.icon" class="size-5 shrink-0" />
              <span v-show="!collapsed">{{ item.label }}</span>
            </a>
          </li>

          <li v-show="!collapsed" class="menu-title">Libraries</li>
          <li v-for="lib in libraries" :key="lib.label">
            <a class="opacity-80" :class="{ 'justify-center px-0': collapsed }">
              <component :is="lib.icon" class="size-5 shrink-0" />
              <span v-show="!collapsed">{{ lib.label }}</span>
              <span v-show="!collapsed" class="badge badge-ghost badge-sm ml-auto">{{ lib.count }}</span>
            </a>
          </li>
        </ul>
      </aside>
    </div>
  </div>
</template>
