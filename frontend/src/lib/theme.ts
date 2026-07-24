// Theming = one full DaisyUI theme at a time (base surfaces + a harmonized
// accent set). Every theme is a 1:1 light/dark pair (`pair` points at its
// counterpart), so the navbar Sun/Moon and the Settings "Mode" toggle simply
// flip a theme to its opposite variant (Nord dark ↔ Nord light).

import { computed, ref } from "vue";

export type Mode = "light" | "dark";
export interface ThemeDef {
  id: string; // also the DaisyUI theme name on <html data-theme>
  name: string;
  mode: Mode;
  pair: string; // the opposite-mode variant of the same family
}

export const THEMES: readonly ThemeDef[] = [
  // Light
  { id: "light", name: "Default", mode: "light", pair: "dark" },
  { id: "nord-light", name: "Nord", mode: "light", pair: "nord" },
  { id: "dracula-light", name: "Alucard", mode: "light", pair: "dracula" },
  { id: "catppuccin-latte", name: "Catppuccin Latte", mode: "light", pair: "catppuccin-mocha" },
  { id: "tokyonight-light", name: "Tokyo Night Day", mode: "light", pair: "tokyonight" },
  { id: "rosepine-dawn", name: "Rosé Pine Dawn", mode: "light", pair: "rosepine" },
  { id: "gruvbox-light", name: "Gruvbox Light", mode: "light", pair: "gruvbox-dark" },
  { id: "solarized-light", name: "Solarized Light", mode: "light", pair: "solarized-dark" },
  // Dark
  { id: "dark", name: "Default", mode: "dark", pair: "light" },
  { id: "nord", name: "Nord", mode: "dark", pair: "nord-light" },
  { id: "dracula", name: "Dracula", mode: "dark", pair: "dracula-light" },
  { id: "catppuccin-mocha", name: "Catppuccin Mocha", mode: "dark", pair: "catppuccin-latte" },
  { id: "tokyonight", name: "Tokyo Night", mode: "dark", pair: "tokyonight-light" },
  { id: "rosepine", name: "Rosé Pine", mode: "dark", pair: "rosepine-dawn" },
  { id: "gruvbox-dark", name: "Gruvbox Dark", mode: "dark", pair: "gruvbox-light" },
  { id: "solarized-dark", name: "Solarized Dark", mode: "dark", pair: "solarized-light" },
];

const KEY = "lychee.theme";
const ids = new Set(THEMES.map((t) => t.id));
const byId = (id: string): ThemeDef => THEMES.find((t) => t.id === id) ?? THEMES[0];

const stored = localStorage.getItem(KEY);
const theme = ref<string>(stored && ids.has(stored) ? stored : "dark");
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
    apply();
  }
  // Flip to the same family's opposite-mode variant.
  function toggleMode(): void {
    setTheme(byId(theme.value).pair);
  }
  function setMode(m: Mode): void {
    if (mode.value !== m) toggleMode();
  }
  return { theme, mode, THEMES, setTheme, setMode, toggleMode };
}
