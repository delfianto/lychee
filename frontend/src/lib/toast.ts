// Minimal toast queue as a module singleton — call `toast(...)` from anywhere;
// <Toaster/> (mounted in the shell) renders and auto-dismisses them.

import { ref } from "vue";

export interface Toast {
  id: number;
  message: string;
  type: "success" | "info" | "error";
}

const toasts = ref<Toast[]>([]);
let seq = 0;

export function useToasts() {
  return toasts;
}

export function toast(message: string, type: Toast["type"] = "success"): void {
  const id = ++seq;
  toasts.value.push({ id, message, type });
  setTimeout(() => {
    toasts.value = toasts.value.filter((t) => t.id !== id);
  }, 2500);
}
