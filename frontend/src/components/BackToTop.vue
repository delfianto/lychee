<script setup lang="ts">
import { ArrowUp } from "@lucide/vue";
import { onBeforeUnmount, onMounted, ref } from "vue";

const visible = ref(false);
function update(): void {
  visible.value = window.scrollY > 600;
}
function goUp(): void {
  window.scrollTo({
    top: 0,
    left: 0,
    behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
  });
}
onMounted(() => {
  update();
  window.addEventListener("scroll", update, { passive: true });
});
onBeforeUnmount(() => window.removeEventListener("scroll", update));
</script>

<template>
  <button
    v-if="visible"
    type="button"
    class="btn btn-circle btn-primary fixed right-4 bottom-5 z-20 size-11 shadow-lg sm:right-6"
    aria-label="Back to top"
    title="Back to top"
    @click="goUp"
  >
    <ArrowUp class="size-5" />
  </button>
</template>
