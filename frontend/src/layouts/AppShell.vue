<script setup lang="ts">
import {
  ArrowLeft,
  Book,
  BookOpen,
  GalleryThumbnails,
  Cherry,
  Dices,
  Heart,
  House,
  Images,
  Layers,
  Menu,
  Moon,
  Search,
  Settings,
  Sun,
} from "lucide-vue-next";
import { type Component, computed, onMounted, ref } from "vue";
import { RouterLink, RouterView, useRoute, useRouter } from "vue-router";

import { connectTaskStream } from "../api/events";
import { randomSeriesId } from "../api/queries";
import ActivityIndicator from "../components/ActivityIndicator.vue";
import Toaster from "../components/Toaster.vue";
import { useTheme } from "../lib/theme";

// Open the shared background-task stream once for the whole app.
onMounted(connectTaskStream);

const router = useRouter();
const route = useRoute();
const { mode, toggleMode } = useTheme();

const isSettings = computed(() => route.path === "/settings");
const mobileOpen = ref(false); // mobile: off-canvas nav drawer

function closeMobile(): void {
  mobileOpen.value = false;
}

async function goRandom(): Promise<void> {
  mobileOpen.value = false;
  const id = await randomSeriesId();
  if (id) void router.push(`/series/${id}`);
}

const searchQuery = ref("");
function goSearch(): void {
  mobileOpen.value = false;
  const q = searchQuery.value.trim();
  void router.push({ path: "/search", query: q ? { q } : {} });
}

interface NavItem {
  label: string;
  icon: Component;
  to?: string; // items without a route yet render as disabled placeholders
}

const nav: NavItem[] = [
  { label: "Home", icon: House, to: "/" },
  { label: "Reading", icon: BookOpen, to: "/reading" },
  { label: "Favorites", icon: Heart, to: "/favorites" },
  { label: "Manga", icon: Book, to: "/manga" },
  { label: "Comics", icon: Images, to: "/comics" },
  { label: "Gallery", icon: GalleryThumbnails, to: "/gallery" },
  { label: "Lists", icon: Layers, to: "/lists" },
];
</script>

<template>
  <div class="drawer">
    <input id="app-drawer" v-model="mobileOpen" type="checkbox" class="drawer-toggle" />

    <!-- App column -->
    <div class="drawer-content flex min-h-dvh flex-col bg-base-200">
      <header class="navbar sticky top-0 z-20 border-b border-base-300 bg-base-100/90 px-2 backdrop-blur sm:px-4">
        <div class="navbar-start w-auto gap-1">
          <label for="app-drawer" class="btn btn-square btn-ghost btn-sm lg:hidden" aria-label="Menu">
            <Menu class="size-5" />
          </label>
          <!-- Static brand — Home is always one click away in the nav, so the
               logo doesn't double as a home link. -->
          <div class="flex select-none items-center gap-2 px-2 text-xl font-bold">
            <Cherry class="size-6 shrink-0 text-primary" /><span class="hidden sm:inline">lychee</span>
          </div>
          <!-- Desktop nav links -->
          <nav class="ml-1 hidden items-center gap-0.5 lg:flex">
            <template v-for="item in nav" :key="item.label">
              <RouterLink
                v-if="item.to"
                :to="item.to"
                class="btn btn-ghost btn-sm gap-1.5"
                active-class="btn-active"
                :exact-active-class="item.to === '/' ? 'btn-active' : undefined"
                :title="item.label"
                :aria-label="item.label"
              >
                <component :is="item.icon" class="size-4" /><span class="hidden xl:inline">{{ item.label }}</span>
              </RouterLink>
              <span v-else class="btn btn-ghost btn-sm gap-1.5 opacity-40">
                <component :is="item.icon" class="size-4" /><span class="hidden xl:inline">{{ item.label }}</span>
              </span>
            </template>
          </nav>
        </div>

        <div class="navbar-end ml-auto w-auto gap-1">
          <label class="input input-bordered input-sm hidden w-44 items-center gap-2 sm:flex lg:w-56">
            <Search class="size-4 opacity-60" />
            <input v-model="searchQuery" type="search" class="grow" placeholder="Search…" aria-label="Search series" @keyup.enter="goSearch" />
          </label>
          <ActivityIndicator />
          <button class="btn btn-circle btn-ghost btn-sm" aria-label="Random series" @click="goRandom">
            <Dices class="size-5" />
          </button>
          <button
            class="btn btn-circle btn-ghost btn-sm"
            :aria-label="mode === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'"
            @click="toggleMode"
          >
            <Sun v-if="mode === 'dark'" class="size-5" />
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

      <main class="grow overflow-x-clip">
        <RouterView v-slot="{ Component }">
          <Transition name="page" mode="out-in">
            <!-- Key by path (not full path) so pages animate on navigation but
                 not on query-only changes like ?view= / ?q=. -->
            <component :is="Component" :key="route.path" />
          </Transition>
        </RouterView>
      </main>
    </div>

    <!-- Mobile nav drawer -->
    <div class="drawer-side z-30">
      <label for="app-drawer" class="drawer-overlay" aria-label="Close menu"></label>
      <aside class="flex min-h-dvh w-64 flex-col bg-base-100 p-2">
        <div class="flex h-14 items-center gap-2 px-2 text-xl font-bold">
          <Cherry class="size-6 shrink-0 text-primary" />lychee
        </div>
        <ul class="menu w-full gap-0.5">
          <li v-for="item in nav" :key="item.label">
            <RouterLink
              v-if="item.to"
              :to="item.to"
              active-class="menu-active"
              :exact-active-class="item.to === '/' ? 'menu-active' : undefined"
              @click="closeMobile"
            >
              <component :is="item.icon" class="size-5 shrink-0" />{{ item.label }}
            </RouterLink>
            <a v-else class="opacity-40">
              <component :is="item.icon" class="size-5 shrink-0" />{{ item.label }}
            </a>
          </li>
        </ul>
      </aside>
    </div>

    <Toaster />
  </div>
</template>
