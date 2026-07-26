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
  /** Gallery lightbox: start playback when a video is opened. */
  videoAutoPlay: boolean;
  /** Gallery lightbox: advance to the next item when a video ends. */
  videoAutoNext: boolean;
}

const KEY = "lychee.reader";
const defaults: ReaderSettings = {
  mode: "single",
  direction: "ltr",
  fit: "height",
  background: "dark",
  videoAutoPlay: true,
  videoAutoNext: true,
};

function load(): ReaderSettings {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) return { ...defaults, ...(JSON.parse(raw) as Partial<ReaderSettings>) };
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
