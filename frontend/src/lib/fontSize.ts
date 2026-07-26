// Root font size (px). The UI is rem-based, so this scales text AND spacing
// together — the same effect as browser zoom, but persisted per user.

import { ref } from "vue";

export const DEFAULT_FONT_SIZE = 16;
export const MIN_FONT_SIZE = 14;
export const MAX_FONT_SIZE = 22;

const KEY = "lychee.fontSize";

function clamp(px: number): number {
  return Math.min(MAX_FONT_SIZE, Math.max(MIN_FONT_SIZE, Math.round(px)));
}

const stored = Number(localStorage.getItem(KEY));
const fontSize = ref(stored ? clamp(stored) : DEFAULT_FONT_SIZE);

function apply(): void {
  document.documentElement.style.fontSize = `${fontSize.value}px`;
}
apply(); // before the app mounts

// Debounced persist: a synchronous localStorage write on every drag `input`
// event is sync I/O on the drag's hot path and can stall it. Applying to the
// DOM stays synchronous so the live rescale is reliable.
let saveTimer: ReturnType<typeof setTimeout> | undefined;
function persist(): void {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => localStorage.setItem(KEY, String(fontSize.value)), 250);
}

export function useFontSize() {
  function setFontSize(px: number): void {
    fontSize.value = clamp(px);
    apply();
    persist();
  }
  function resetFontSize(): void {
    setFontSize(DEFAULT_FONT_SIZE);
  }
  return { fontSize, setFontSize, resetFontSize };
}
