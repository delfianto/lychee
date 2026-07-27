// Traps Tab/Shift+Tab focus inside a modal while it's open, and restores focus to
// whatever triggered it on close. None of the modal components had this — a keyboard
// user could Tab out of an open dialog into the (still-interactive) page behind it.

import { type Ref, onUnmounted, watch } from "vue";

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

function focusables(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
    (el) => el.offsetParent !== null, // skip hidden elements
  );
}

/** @param container the modal's own box (not the backdrop) · @param active whether the modal is open */
export function useFocusTrap(container: Ref<HTMLElement | null>, active: Ref<boolean>): void {
  let previouslyFocused: HTMLElement | null = null;
  let trapping = false;

  function onKeydown(e: KeyboardEvent): void {
    if (e.key !== "Tab" || !container.value) return;
    const els = focusables(container.value);
    if (!els.length) return;
    const first = els[0]!;
    const last = els[els.length - 1]!;
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }

  function activate(): void {
    if (trapping) return;
    trapping = true;
    previouslyFocused = document.activeElement as HTMLElement | null;
    document.addEventListener("keydown", onKeydown);
    requestAnimationFrame(() => container.value && focusables(container.value)[0]?.focus());
  }

  // Some modals have no `open` prop — the parent mounts them only while shown, so
  // `active` is a static `true` that never flips and the `watch` below never fires
  // its "closed" branch. `onUnmounted` covers that case (and is a harmless no-op,
  // guarded by `trapping`, for modals that *do* toggle `active` before unmounting).
  function deactivate(): void {
    if (!trapping) return;
    trapping = false;
    document.removeEventListener("keydown", onKeydown);
    previouslyFocused?.focus();
    previouslyFocused = null;
  }

  watch(active, (isActive) => (isActive ? activate() : deactivate()), { immediate: true });
  onUnmounted(deactivate);
}
