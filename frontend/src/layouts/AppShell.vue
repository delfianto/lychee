<script setup lang="ts">
import {
  ArrowLeft,
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
  Moon,
  Search,
  Settings,
  Sun,
} from "lucide-vue-next";
import { type Component, computed, ref } from "vue";
import { RouterLink, RouterView, useRoute, useRouter } from "vue-router";

import { useTheme } from "../lib/theme";
import { randomSeriesId } from "../mocks/library";

const router = useRouter();
const route = useRoute();
const { theme, toggle } = useTheme();

const isSettings = computed(() => route.path === "/settings");

const collapsed = ref(false); // desktop: collapse to an icon rail
const mobileOpen = ref(false); // mobile: off-canvas drawer

function closeMobile(): void {
  mobileOpen.value = false;
}

function goRandom(): void {
  mobileOpen.value = false;
  void router.push(`/series/${randomSeriesId()}`);
}

interface NavItem {
  label: string;
  icon: Component;
  to?: string;
  action?: () => void;
}

// Primary nav (items without `to`/`action` are placeholders until built).
const primary: NavItem[] = [
  { label: "Home", icon: House, to: "/" },
  { label: "Favorites", icon: Heart, to: "/favorites" },
  { label: "Browse", icon: Compass, to: "/browse" },
  { label: "Search", icon: Search },
  { label: "Reading", icon: BookOpen, to: "/reading" },
  { label: "Random", icon: Dices, action: goRandom },
];

const libraries: { label: string; icon: Component; count: number; to?: string }[] = [
  { label: "Lists", icon: List, count: 4 },
  { label: "Manga", icon: Book, count: 128, to: "/manga" },
  { label: "Comics", icon: Images, count: 42, to: "/comics" },
  { label: "Books", icon: Library, count: 17, to: "/books" },
];
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
        </div>
        <div class="navbar-end gap-1">
          <label class="input input-bordered input-sm hidden w-56 items-center gap-2 sm:flex md:w-64">
            <Search class="size-4 opacity-60" />
            <input type="search" class="grow" placeholder="Search…" />
          </label>
          <button
            class="btn btn-circle btn-ghost btn-sm"
            :aria-label="theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'"
            @click="toggle"
          >
            <Sun v-if="theme === 'dark'" class="size-5" />
            <Moon v-else class="size-5" />
          </button>
          <RouterLink
            v-if="!isSettings"
            to="/settings"
            class="btn btn-circle btn-ghost btn-sm"
            aria-label="Settings"
          >
            <Settings class="size-5" />
          </RouterLink>
          <button v-else class="btn btn-circle btn-ghost btn-sm" aria-label="Back" @click="router.back()">
            <ArrowLeft class="size-5" />
          </button>
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
              :to="item.to"
              active-class="menu-active"
              :exact-active-class="item.to === '/' ? 'menu-active' : undefined"
              :class="{ 'justify-center px-0': collapsed }"
              @click="closeMobile"
            >
              <component :is="item.icon" class="size-5 shrink-0" />
              <span v-show="!collapsed">{{ item.label }}</span>
            </RouterLink>
            <a
              v-else-if="item.action"
              class="cursor-pointer"
              :class="{ 'justify-center px-0': collapsed }"
              @click="item.action"
            >
              <component :is="item.icon" class="size-5 shrink-0" />
              <span v-show="!collapsed">{{ item.label }}</span>
            </a>
            <a v-else class="opacity-80" :class="{ 'justify-center px-0': collapsed }">
              <component :is="item.icon" class="size-5 shrink-0" />
              <span v-show="!collapsed">{{ item.label }}</span>
            </a>
          </li>

          <li v-show="!collapsed" class="menu-title">Libraries</li>
          <li v-for="lib in libraries" :key="lib.label">
            <RouterLink
              v-if="lib.to"
              :to="lib.to"
              active-class="menu-active"
              :class="{ 'justify-center px-0': collapsed }"
              @click="closeMobile"
            >
              <component :is="lib.icon" class="size-5 shrink-0" />
              <span v-show="!collapsed">{{ lib.label }}</span>
              <span v-show="!collapsed" class="badge badge-ghost badge-sm ml-auto">{{ lib.count }}</span>
            </RouterLink>
            <a v-else class="opacity-80" :class="{ 'justify-center px-0': collapsed }">
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
