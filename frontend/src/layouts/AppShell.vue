<script setup lang="ts">
import { RouterLink, RouterView } from "vue-router";

// Primary nav (only routed items link; the rest are placeholders until built).
const primary = [
  { label: "Home", icon: "🏠", to: "/" },
  { label: "Favorites", icon: "♥" },
  { label: "Browse", icon: "🔎", to: "/browse" },
  { label: "Search", icon: "⌕" },
  { label: "Reading", icon: "📖" },
  { label: "Random", icon: "🎲" },
  { label: "Settings", icon: "⚙" },
];

const libraries = [
  { label: "Lists", icon: "☰", count: 4 },
  { label: "Manga", icon: "📚", count: 128 },
  { label: "Comics", icon: "🦸", count: 42 },
  { label: "Books", icon: "📕", count: 17 },
];
</script>

<template>
  <div class="flex min-h-dvh bg-base-200">
    <!-- Sidebar -->
    <aside class="hidden w-64 shrink-0 border-r border-base-300 bg-base-100 lg:block">
      <div class="flex h-14 items-center gap-2 px-4 text-xl font-bold">🍒 lychee</div>
      <ul class="menu w-full gap-0.5 px-2">
        <li v-for="item in primary" :key="item.label">
          <RouterLink v-if="item.to" :to="item.to!" active-class="menu-active" :exact-active-class="item.to === '/' ? 'menu-active' : undefined">
            <span class="w-5 text-center">{{ item.icon }}</span>{{ item.label }}
          </RouterLink>
          <a v-else class="opacity-80"><span class="w-5 text-center">{{ item.icon }}</span>{{ item.label }}</a>
        </li>

        <li class="menu-title">Libraries</li>
        <li v-for="lib in libraries" :key="lib.label">
          <a class="opacity-80">
            <span class="w-5 text-center">{{ lib.icon }}</span>{{ lib.label }}
            <span class="badge badge-sm badge-ghost ml-auto">{{ lib.count }}</span>
          </a>
        </li>
      </ul>
    </aside>

    <!-- Content column -->
    <div class="flex min-w-0 grow flex-col">
      <!-- Top navbar -->
      <header class="navbar sticky top-0 z-10 border-b border-base-300 bg-base-100/90 backdrop-blur">
        <div class="navbar-start">
          <label class="input input-bordered input-sm hidden items-center gap-2 sm:flex">
            <span class="opacity-60">⌕</span>
            <input type="search" class="grow" placeholder="Search…" />
          </label>
        </div>
        <div class="navbar-end gap-1">
          <button class="btn btn-ghost btn-circle btn-sm tooltip tooltip-bottom" data-tip="Random">🎲</button>
          <button class="btn btn-ghost btn-circle btn-sm">⚙</button>
          <div class="avatar avatar-placeholder">
            <div class="w-8 rounded-full bg-neutral text-neutral-content">
              <span class="text-xs">U</span>
            </div>
          </div>
        </div>
      </header>

      <main class="grow overflow-x-hidden">
        <RouterView />
      </main>
    </div>
  </div>
</template>
