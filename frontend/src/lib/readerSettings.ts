// Reader preferences as a shared, persisted reactive singleton — used by both
// the manga reader and Settings → General (reader / video) so they stay in sync.

import { reactive, watch } from "vue";

export type ReaderMode = "single" | "double" | "longstrip";
export type ReaderDirection = "ltr" | "rtl";
export type ReaderFit = "width" | "height" | "both" | "original";
export type ReaderBackground = "dark" | "black" | "sepia";

export interface ReaderSettings {
  mode: ReaderMode;
  direction: ReaderDirection;
  fit: ReaderFit;
  background: ReaderBackground;
  /** Ad-hoc reading (Neko style): number of pages to prefetch into temp/ (1–20). */
  preloadPages: number;
  /** Gallery lightbox: start playback when a video is opened. */
  videoAutoPlay: boolean;
  /** Gallery lightbox: advance to the next item when a video ends. */
  videoAutoNext: boolean;
}

export const MIN_PRELOAD_PAGES = 1;
export const MAX_PRELOAD_PAGES = 20;

export function clampPreloadPages(value: unknown): number {
  const num = Number(value);
  if (!Number.isFinite(num)) return 4;
  return Math.max(MIN_PRELOAD_PAGES, Math.min(MAX_PRELOAD_PAGES, Math.round(num)));
}

const KEY = "lychee.reader";
const defaults: ReaderSettings = {
  mode: "single",
  direction: "ltr",
  fit: "height",
  background: "dark",
  preloadPages: 4,
  videoAutoPlay: true,
  videoAutoNext: true,
};

function load(): ReaderSettings {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<ReaderSettings>;
      return {
        ...defaults,
        ...parsed,
        preloadPages:
          parsed.preloadPages !== undefined
            ? clampPreloadPages(parsed.preloadPages)
            : defaults.preloadPages,
      };
    }
  } catch {
    /* fall through to defaults */
  }
  return { ...defaults };
}

const settings = reactive<ReaderSettings>(load());
watch(settings, () => localStorage.setItem(KEY, JSON.stringify(settings)), { deep: true });

export function useReaderSettings(): ReaderSettings {
  return settings;
}
