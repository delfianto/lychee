import { expect, it, vi } from "vite-plus/test";
import { createProgressWriter } from "./readingProgress";

it("serializes requests and coalesces a chapter to its furthest completed position", async () => {
  let release!: () => void;
  const send = vi
    .fn()
    .mockImplementationOnce(
      () =>
        new Promise<void>((resolve) => {
          release = resolve;
        }),
    )
    .mockResolvedValue(undefined);
  const status = vi.fn();
  const writer = createProgressWriter(send, status);
  writer.record("a", 1);
  writer.record("a", 2);
  writer.record("a", 6, true);
  writer.record("a", 3);
  writer.record("b", 1);
  expect(send).toHaveBeenCalledTimes(1);
  const saving = writer.flush();
  release();
  expect(await saving).toBe(true);
  expect(send.mock.calls).toEqual([
    ["a", 1, undefined],
    ["a", 6, true],
    ["b", 1, undefined],
  ]);
  writer.record("a", 6, true);
  expect(send).toHaveBeenCalledTimes(3);
});

it("keeps failed writes for retry and reports success after a retry", async () => {
  const send = vi.fn().mockRejectedValueOnce(new Error("Offline")).mockResolvedValue(undefined);
  const status = vi.fn();
  const writer = createProgressWriter(send, status);
  writer.record("a", 3, true);
  expect(await writer.flush()).toBe(false);
  expect(status).toHaveBeenLastCalledWith("Offline");
  expect(await writer.flush()).toBe(true);
  expect(send).toHaveBeenLastCalledWith("a", 3, true);
  expect(status).toHaveBeenLastCalledWith(null);
});

it("flushes pending work on tab close and handles non-Error failures", async () => {
  let reject!: (error: unknown) => void;
  const send = vi
    .fn()
    .mockImplementationOnce(
      () =>
        new Promise<void>((_resolve, fail) => {
          reject = fail;
        }),
    )
    .mockRejectedValue("closed");
  const status = vi.fn();
  const writer = createProgressWriter(send, status);
  writer.record("a", 1);
  writer.record("a", 2);
  writer.finish();
  expect(send).toHaveBeenLastCalledWith("a", 2, undefined);
  reject("Offline");
  expect(await writer.flush()).toBe(false);
  expect(status).toHaveBeenLastCalledWith("Couldn’t save reading progress");
});
