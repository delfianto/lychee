// Theme = mode (light/dark base surfaces) × color scheme (accent palette),
// kept as two independent axes like TBM. Both persist and are mirrored onto
// <html data-theme> (mode) and <html data-scheme> (accent, see style.css).

import { ref } from "vue";

export type Mode = "light" | "dark";

// Accent schemes — each works in both light and dark. "default" = DaisyUI's own.
export const COLOR_SCHEMES = ["default", "emerald", "teal", "sky", "violet", "rose", "amber"] as const;
export type Scheme = (typeof COLOR_SCHEMES)[number];

const MODE_KEY = "lychee.mode";
const SCHEME_KEY = "lychee.scheme";

function loadMode(): Mode {
  const s = localStorage.getItem(MODE_KEY);
  return s === "light" || s === "dark" ? s : "dark";
}
function loadScheme(): Scheme {
  const s = localStorage.getItem(SCHEME_KEY) ?? "";
  return (COLOR_SCHEMES as readonly string[]).includes(s) ? (s as Scheme) : "default";
}

const mode = ref<Mode>(loadMode());
const scheme = ref<Scheme>(loadScheme());

function apply(): void {
  const el = document.documentElement;
  el.setAttribute("data-theme", mode.value);
  el.setAttribute("data-scheme", scheme.value);
}
apply(); // set on first import, before the shell mounts

export function useTheme() {
  function setMode(m: Mode): void {
    mode.value = m;
    localStorage.setItem(MODE_KEY, m);
    apply();
  }
  function toggleMode(): void {
    setMode(mode.value === "dark" ? "light" : "dark");
  }
  function setScheme(s: Scheme): void {
    scheme.value = s;
    localStorage.setItem(SCHEME_KEY, s);
    apply();
  }
  return { mode, scheme, setMode, toggleMode, setScheme };
}
