// Theming = one full DaisyUI theme at a time (base surfaces + a harmonized
// accent set), chosen from a curated set of popular community themes. Light and
// dark are not a separate axis anymore: each theme is inherently light or dark.
// The navbar Sun/Moon is a "smart toggle" — it remembers the last light theme
// and last dark theme you picked and flips between those two.

import { computed, ref } from "vue";

export type Mode = "light" | "dark";
export interface ThemeDef {
  id: string; // also the DaisyUI theme name applied to <html data-theme>
  name: string;
  mode: Mode;
}

export const THEMES: readonly ThemeDef[] = [
  // Light
  { id: "light", name: "Default", mode: "light" },
  { id: "catppuccin-latte", name: "Catppuccin Latte", mode: "light" },
  { id: "rosepine-dawn", name: "Rosé Pine Dawn", mode: "light" },
  { id: "gruvbox-light", name: "Gruvbox Light", mode: "light" },
  { id: "solarized-light", name: "Solarized Light", mode: "light" },
  // Dark
  { id: "dark", name: "Default", mode: "dark" },
  { id: "nord", name: "Nord", mode: "dark" },
  { id: "dracula", name: "Dracula", mode: "dark" },
  { id: "catppuccin-mocha", name: "Catppuccin Mocha", mode: "dark" },
  { id: "tokyonight", name: "Tokyo Night", mode: "dark" },
  { id: "rosepine", name: "Rosé Pine", mode: "dark" },
  { id: "gruvbox-dark", name: "Gruvbox Dark", mode: "dark" },
  { id: "solarized-dark", name: "Solarized Dark", mode: "dark" },
];

const KEY = "lychee.theme";
const LIGHT_KEY = "lychee.theme.light";
const DARK_KEY = "lychee.theme.dark";

const ids = new Set(THEMES.map((t) => t.id));
const byId = (id: string): ThemeDef => THEMES.find((t) => t.id === id) ?? THEMES[0];
const valid = (id: string | null, fallback: string): string => (id && ids.has(id) ? id : fallback);

const theme = ref<string>(valid(localStorage.getItem(KEY), "dark"));
// Remembered pick per mode, so the light/dark toggle flips between them.
const lightPref = ref<string>(valid(localStorage.getItem(LIGHT_KEY), "light"));
const darkPref = ref<string>(valid(localStorage.getItem(DARK_KEY), "dark"));

const mode = computed<Mode>(() => byId(theme.value).mode);

function apply(): void {
  document.documentElement.setAttribute("data-theme", theme.value);
}
apply(); // before the app mounts

export function useTheme() {
  function setTheme(id: string): void {
    if (!ids.has(id)) return;
    theme.value = id;
    localStorage.setItem(KEY, id);
    if (byId(id).mode === "light") {
      lightPref.value = id;
      localStorage.setItem(LIGHT_KEY, id);
    } else {
      darkPref.value = id;
      localStorage.setItem(DARK_KEY, id);
    }
    apply();
  }
  function setMode(m: Mode): void {
    setTheme(m === "light" ? lightPref.value : darkPref.value);
  }
  function toggleMode(): void {
    setMode(mode.value === "dark" ? "light" : "dark");
  }
  return { theme, mode, THEMES, setTheme, setMode, toggleMode };
}
