import { afterEach, expect, it, vi } from "vite-plus/test";

afterEach(() => vi.useRealTimers());
it("shares the queue and expires each toast by id, with longer-lived errors", async () => {
  vi.resetModules();
  vi.useFakeTimers();
  const { toast, useToasts } = await import("./toast");
  toast("Saved");
  toast("Try again", "error");
  vi.advanceTimersByTime(1000);
  toast("Syncing", "info");
  expect(useToasts().value.map((t) => t.type)).toEqual(["success", "error", "info"]);
  expect(new Set(useToasts().value.map((t) => t.id)).size).toBe(3);
  vi.advanceTimersByTime(1500);
  expect(useToasts().value.map((t) => t.message)).toEqual(["Try again", "Syncing"]);
  vi.advanceTimersByTime(1000);
  expect(useToasts().value.map((t) => t.message)).toEqual(["Try again"]);
  vi.advanceTimersByTime(1000);
  expect(useToasts().value).toEqual([]);
});
