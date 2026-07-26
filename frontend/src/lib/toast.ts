// Minimal toast queue as a module singleton — call `toast(...)` from anywhere;
// <Toaster/> (mounted in the shell) renders and auto-dismisses them.

import { ref } from "vue";

export type ToastType = "success" | "info" | "error";

export interface Toast {
  id: number;
  message: string;
  type: ToastType;
}

const toasts = ref<Toast[]>([]);
let seq = 0;

export function useToasts() {
  return toasts;
}

export function toast(message: string, type: ToastType = "success"): void {
  const id = ++seq;
  toasts.value.push({ id, message, type });
  // Errors stay a bit longer so multi-line messages (e.g. missing manga library) can be read.
  const ms = type === "error" ? 4500 : 2500;
  setTimeout(() => {
    toasts.value = toasts.value.filter((t) => t.id !== id);
  }, ms);
}
