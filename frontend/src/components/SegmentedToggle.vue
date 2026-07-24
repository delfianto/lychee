<script setup lang="ts" generic="T extends string">
import type { Component } from "vue";

// Single-select segmented control shared by the density/view/theme/reader
// toggles. Styling lives in `.segmented` (style.css) so every instance matches
// the card border weight. Options with an `icon` render icon-only (label →
// aria-label); otherwise the label text is shown.
defineProps<{
  options: readonly { value: T; label: string; icon?: Component }[];
  modelValue: T;
  ariaLabel?: string;
  block?: boolean;
}>();
defineEmits<{ "update:modelValue": [T] }>();
</script>

<template>
  <div class="segmented" :class="{ 'is-block': block }" role="group" :aria-label="ariaLabel">
    <button
      v-for="o in options"
      :key="o.value"
      type="button"
      :class="{ 'is-active': o.value === modelValue }"
      :aria-pressed="o.value === modelValue"
      :aria-label="o.icon ? o.label : undefined"
      :title="o.icon ? o.label : undefined"
      @click="$emit('update:modelValue', o.value)"
    >
      <component :is="o.icon" v-if="o.icon" class="size-4" />
      <span v-else>{{ o.label }}</span>
    </button>
  </div>
</template>
