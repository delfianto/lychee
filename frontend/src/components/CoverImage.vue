<script setup lang="ts">
import { ImageOff } from "lucide-vue-next";
import { ref, watch } from "vue";

const props = withDefaults(
  defineProps<{
    src: string;
    alt?: string;
    /** Extra classes on the outer shell (size, rounded, etc.). */
    class?: string;
    /** Skip lazy loading for LCP / hero covers. */
    priority?: boolean;
  }>(),
  { alt: "", priority: false },
);

const loaded = ref(false);
const failed = ref(false);

watch(
  () => props.src,
  () => {
    loaded.value = false;
    failed.value = false;
  },
);

function onLoad(): void {
  loaded.value = true;
}
function onError(): void {
  failed.value = true;
  loaded.value = false;
}
</script>

<template>
  <div
    class="relative overflow-hidden bg-base-300"
    :class="props.class"
  >
    <!-- Shimmer while the cover bytes are still materializing / transferring -->
    <div
      v-if="!loaded && !failed"
      class="cover-shimmer absolute inset-0"
      aria-hidden="true"
    />
    <img
      v-if="!failed"
      :src="src"
      :alt="alt"
      class="absolute inset-0 h-full w-full object-cover transition-opacity duration-300"
      :class="loaded ? 'opacity-100' : 'opacity-0'"
      :loading="priority ? 'eager' : 'lazy'"
      decoding="async"
      @load="onLoad"
      @error="onError"
    />
    <div
      v-else
      class="absolute inset-0 flex items-center justify-center text-base-content/30"
      aria-hidden="true"
    >
      <ImageOff class="size-6" />
    </div>
  </div>
</template>
