<script setup lang="ts">
// Full-screen gallery viewer: stills/GIFs as <img>, progressive MP4 via Plyr
// (polished controls). Prev/next, Esc, counter. Honors Settings → Reader video
// (auto play / auto next). Plyr is destroyed on index change.
import { ChevronLeft, ChevronRight, X } from "lucide-vue-next";
import Plyr from "plyr";
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";

import { useReaderSettings } from "../lib/readerSettings";
import type { GalleryMediaItem } from "../types";

import "plyr/dist/plyr.css";

const props = defineProps<{ items: GalleryMediaItem[]; index: number }>();
const emit = defineEmits<{ close: []; "update:index": [number] }>();

const reader = useReaderSettings();
const videoEl = ref<HTMLVideoElement | null>(null);
let player: Plyr | null = null;

const current = () => props.items[props.index];

function destroyPlayer(): void {
  if (player) {
    try {
      player.off("ended", onVideoEnded);
      player.destroy();
    } catch {
      /* already torn down */
    }
    player = null;
  }
}

function onVideoEnded(): void {
  if (!reader.videoAutoNext) return;
  go(1);
}

async function mountPlayer(): Promise<void> {
  destroyPlayer();
  await nextTick();
  const el = videoEl.value;
  if (!el || current()?.kind !== "video") return;
  player = new Plyr(el, {
    controls: [
      "play-large",
      "play",
      "progress",
      "current-time",
      "duration",
      "mute",
      "volume",
      "settings",
      "pip",
      "fullscreen",
    ],
    autoplay: reader.videoAutoPlay,
    hideControls: false,
    resetOnEnd: false,
    keyboard: { focused: true, global: false },
    tooltips: { controls: true, seek: true },
  });
  player.on("ended", onVideoEnded);
  // Opening the lightbox is a user gesture; reinforce autoplay if the browser
  // ignored the autoplay attribute (common when the media element is recreated).
  if (reader.videoAutoPlay) {
    player.on("ready", () => {
      void player?.play()?.catch(() => {
        /* autoplay blocked — user can hit play */
      });
    });
  }
}

function go(delta: number): void {
  const n = props.items.length;
  if (n === 0) return;
  emit("update:index", (props.index + delta + n) % n);
}

function onKey(e: KeyboardEvent): void {
  if (e.key === "Escape") {
    emit("close");
    return;
  }
  // When Plyr has focus it owns Space / arrows for seek; still allow neighbor
  // navigation when the event target is not inside the player.
  const inPlayer = (e.target as HTMLElement | null)?.closest?.(".plyr");
  if (inPlayer) return;
  if (e.key === "ArrowLeft") go(-1);
  else if (e.key === "ArrowRight") go(1);
}

watch(
  () => [props.index, props.items] as const,
  () => {
    void mountPlayer();
  },
);

onMounted(() => {
  window.addEventListener("keydown", onKey);
  void mountPlayer();
});
onBeforeUnmount(() => {
  window.removeEventListener("keydown", onKey);
  destroyPlayer();
});
</script>

<template>
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/90 p-4"
    @click.self="emit('close')"
  >
    <button
      class="btn btn-circle btn-ghost absolute top-3 right-3 text-white"
      aria-label="Close"
      @click="emit('close')"
    >
      <X class="size-6" />
    </button>
    <button
      class="btn btn-circle btn-ghost absolute top-1/2 left-3 -translate-y-1/2 text-white"
      aria-label="Previous"
      @click="go(-1)"
    >
      <ChevronLeft class="size-7" />
    </button>

    <img
      v-if="current()?.kind !== 'video'"
      :src="current()?.url"
      :alt="`Item ${index + 1} of ${items.length}`"
      class="max-h-[90vh] max-w-[90vw] rounded object-contain shadow-2xl"
    />
    <div
      v-else
      class="lychee-plyr w-full max-w-[min(90vw,56rem)]"
      @click.stop
    >
      <video
        :key="`${index}-${current()?.url}`"
        ref="videoEl"
        playsinline
        preload="metadata"
        :autoplay="reader.videoAutoPlay"
        :poster="current()?.posterUrl ?? current()?.thumbUrl ?? undefined"
        :src="current()?.url"
        class="max-h-[80vh] w-full"
      />
    </div>

    <button
      class="btn btn-circle btn-ghost absolute top-1/2 right-3 -translate-y-1/2 text-white"
      aria-label="Next"
      @click="go(1)"
    >
      <ChevronRight class="size-7" />
    </button>
    <div
      class="absolute bottom-4 left-1/2 -translate-x-1/2 rounded-full bg-black/50 px-3 py-1 text-xs text-white/80"
    >
      {{ index + 1 }} / {{ items.length }}
    </div>
  </div>
</template>

<style scoped>
/* Dark lightbox-friendly Plyr chrome */
.lychee-plyr :deep(.plyr) {
  --plyr-color-main: var(--color-primary);
  --plyr-video-background: #000;
  border-radius: 0.5rem;
  overflow: hidden;
}
.lychee-plyr :deep(.plyr__video-wrapper) {
  background: #000;
}
</style>
