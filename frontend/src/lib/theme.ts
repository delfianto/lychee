// App theme (dark/light) as a tiny module singleton: the ref is shared across
// callers, persisted to localStorage, and mirrored onto <html data-theme>.

import { ref } from "vue";

type Theme = "dark" | "light";
const KEY = "lychee.theme";

const theme = ref<Theme>(localStorage.getItem(KEY) === "light" ? "light" : "dark");

function apply(t: Theme): void {
  document.documentElement.setAttribute("data-theme", t);
}
apply(theme.value); // set on first import, before the shell mounts

export function useTheme() {
  function toggle(): void {
    theme.value = theme.value === "dark" ? "light" : "dark";
    localStorage.setItem(KEY, theme.value);
    apply(theme.value);
  }
  return { theme, toggle };
}
