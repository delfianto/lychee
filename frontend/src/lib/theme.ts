// App theme as a shared module singleton: persisted to localStorage and mirrored
// onto <html data-theme>. Supports any of the enabled DaisyUI color schemes.

import { ref } from "vue";

// Curated set of popular DaisyUI themes (must match the `themes:` list in style.css).
export const COLOR_SCHEMES = [
  "dark",
  "light",
  "cupcake",
  "synthwave",
  "retro",
  "cyberpunk",
  "valentine",
  "dracula",
  "aqua",
  "forest",
  "night",
  "coffee",
  "nord",
  "business",
  "luxury",
  "dim",
] as const;
export type Theme = (typeof COLOR_SCHEMES)[number];

const KEY = "lychee.theme";

function isTheme(v: string | null): v is Theme {
  return v !== null && (COLOR_SCHEMES as readonly string[]).includes(v);
}

const stored = localStorage.getItem(KEY);
const theme = ref<Theme>(isTheme(stored) ? stored : "dark");

function apply(t: Theme): void {
  document.documentElement.setAttribute("data-theme", t);
}
apply(theme.value); // set on first import, before the shell mounts

export function useTheme() {
  function setTheme(t: Theme): void {
    theme.value = t;
    localStorage.setItem(KEY, t);
    apply(t);
  }
  // Navbar quick light/dark switch (colored schemes fall back to light).
  function toggle(): void {
    setTheme(theme.value === "light" ? "dark" : "light");
  }
  return { theme, setTheme, toggle };
}
