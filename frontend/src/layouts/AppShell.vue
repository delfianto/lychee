<script setup lang="ts">
import { ref } from "vue";
import { RouterLink, RouterView } from "vue-router";

// Primary nav (only routed items link; the rest are placeholders until built).
const primary = [
  { label: "Home", icon: "🏠", to: "/" },
  { label: "Favorites", icon: "♥" },
  { label: "Browse", icon: "🔎", to: "/browse" },
  { label: "Search", icon: "⌕" },
  { label: "Reading", icon: "📖" },
  { label: "Random", icon: "🎲" },
  { label: "Settings", icon: "⚙", to: "/settings" },
];

const libraries = [
  { label: "Lists", icon: "☰", count: 4 },
  { label: "Manga", icon: "📚", count: 128 },
  { label: "Comics", icon: "🦸", count: 42 },
  { label: "Books", icon: "📕", count: 17 },
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
          <!-- Mobile: open drawer -->
          <label for="app-drawer" class="btn btn-square btn-ghost btn-sm lg:hidden" aria-label="Menu">☰</label>
          <!-- Desktop: collapse / expand rail -->
          <button
            class="btn btn-square btn-ghost btn-sm hidden lg:inline-flex"
            aria-label="Toggle sidebar"
            @click="collapsed = !collapsed"
          >
            {{ collapsed ? "»" : "«" }}
          </button>
          <label class="input input-bordered input-sm ml-1 hidden items-center gap-2 sm:flex">
            <span class="opacity-60">⌕</span>
            <input type="search" class="grow" placeholder="Search…" />
          </label>
        </div>
        <div class="navbar-end gap-1">
          <button class="btn btn-circle btn-ghost btn-sm" aria-label="Random">🎲</button>
          <RouterLink to="/settings" class="btn btn-circle btn-ghost btn-sm" aria-label="Settings">⚙</RouterLink>
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
          <span>🍒</span><span v-show="!collapsed">lychee</span>
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
              <span class="w-5 shrink-0 text-center">{{ item.icon }}</span>
              <span v-show="!collapsed">{{ item.label }}</span>
            </RouterLink>
            <a v-else class="opacity-80" :class="{ 'justify-center px-0': collapsed }">
              <span class="w-5 shrink-0 text-center">{{ item.icon }}</span>
              <span v-show="!collapsed">{{ item.label }}</span>
            </a>
          </li>

          <li v-show="!collapsed" class="menu-title">Libraries</li>
          <li v-for="lib in libraries" :key="lib.label">
            <a class="opacity-80" :class="{ 'justify-center px-0': collapsed }">
              <span class="w-5 shrink-0 text-center">{{ lib.icon }}</span>
              <span v-show="!collapsed">{{ lib.label }}</span>
              <span v-show="!collapsed" class="badge badge-ghost badge-sm ml-auto">{{ lib.count }}</span>
            </a>
          </li>
        </ul>
      </aside>
    </div>
  </div>
</template>
