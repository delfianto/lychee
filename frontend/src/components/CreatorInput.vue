<script setup lang="ts">
import { onBeforeUnmount, ref, useId, watch } from "vue";
import { fetchCreatorNames } from "../api/queries";
import { createStaleGuard } from "../lib/staleGuard";

const props = defineProps<{ role: "author" | "artist"; modelValue: string }>();
const emit = defineEmits<{ "update:modelValue": [value: string] }>();
const id = useId();
const names = ref<string[]>([]);
const guard = createStaleGuard();
let timer: ReturnType<typeof setTimeout> | undefined;
async function load(): Promise<void> {
  const token = guard.next();
  try {
    const options = await fetchCreatorNames(props.role, props.modelValue);
    if (guard.isCurrent(token)) names.value = options;
  } catch {
    if (guard.isCurrent(token)) names.value = [];
  }
}
watch(
  () => props.modelValue,
  () => {
    guard.next();
    clearTimeout(timer);
    timer = setTimeout(() => void load(), 200);
  },
);
onBeforeUnmount(() => {
  clearTimeout(timer);
  guard.next();
});
</script>

<template>
  <label class="flex min-w-0 flex-col gap-1.5 text-sm">
    <span class="text-base-content/65">{{
      role === "author" ? "Author / mangaka" : "Artist"
    }}</span>
    <input
      :value="modelValue"
      :list="id"
      :aria-label="role === 'author' ? 'Author / mangaka' : 'Artist'"
      type="text"
      autocomplete="off"
      class="input h-10 w-full bg-base-200"
      placeholder="Any — type a name…"
      @focus="load"
      @input="emit('update:modelValue', ($event.target as HTMLInputElement).value)"
    />
    <datalist :id="id"><option v-for="name in names" :key="name" :value="name" /></datalist>
  </label>
</template>
