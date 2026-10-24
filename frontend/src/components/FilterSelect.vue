<script setup lang="ts">
import { Check } from "@lucide/vue";
import { computed } from "vue";
import FilterDropdown from "./FilterDropdown.vue";
const props = defineProps<{
  label: string;
  options: { value: string; label: string }[];
  selected: ReadonlySet<string>;
}>();
const emit = defineEmits<{ toggle: [value: string] }>();
const summary = computed(() => {
  const labels = props.options
    .filter((option) => props.selected.has(option.value))
    .map((option) => option.label);
  if (!labels.length) return "Any";
  return labels.length === 1 ? labels[0]! : `${labels[0]} +${labels.length - 1}`;
});
function clear(): void {
  for (const value of props.selected) emit("toggle", value);
}
</script>

<template>
  <FilterDropdown :label="label" :summary="summary" :count="selected.size">
    <button
      type="button"
      class="btn btn-ghost btn-sm w-full justify-start font-normal"
      @click="clear"
    >
      Any
    </button>
    <button
      v-for="option in options"
      :key="option.value"
      type="button"
      role="checkbox"
      :aria-checked="selected.has(option.value)"
      class="flex w-full items-center gap-2 rounded-field px-2 py-2 text-left text-sm hover:bg-base-200 focus-visible:outline-primary"
      @click="emit('toggle', option.value)"
    >
      <span
        class="flex size-4 shrink-0 items-center justify-center rounded-sm border border-base-content/30"
        :class="{ 'border-primary bg-primary text-primary-content': selected.has(option.value) }"
        ><Check v-if="selected.has(option.value)" class="size-3"
      /></span>
      {{ option.label }}
    </button>
  </FilterDropdown>
</template>
