import { flushPromises } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vite-plus/test";

import type { Task } from "./events";

const { fetchTasks } = vi.hoisted(() => ({ fetchTasks: vi.fn() }));
vi.mock("./client", () => ({ api: { GET: fetchTasks } }));

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((e: MessageEvent<string>) => void) | null = null;
  readonly url: string;
  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }
  /** Simulate the backend pushing `{event, task}` over the wire. */
  emit(event: string, task: Task): void {
    this.onmessage?.(new MessageEvent("message", { data: JSON.stringify({ event, task }) }));
  }
  emitRaw(data: string): void {
    this.onmessage?.(new MessageEvent("message", { data }));
  }
}

function task(id: string, overrides: Partial<Task> = {}): Task {
  return { id, kind: "scan", label: `Task ${id}`, status: "running", progress: 0, ...overrides };
}

beforeEach(() => {
  fetchTasks.mockResolvedValue({ data: [] });
  vi.resetModules(); // `source`/`tasks` are module-level singletons seeded on connect
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
});

describe("connectTaskStream", () => {
  it("is idempotent — a second call does not open a second connection", async () => {
    const { connectTaskStream } = await import("./events");
    connectTaskStream();
    connectTaskStream();
    expect(FakeEventSource.instances).toHaveLength(1);
  });
});

describe("upsert (via incoming SSE messages)", () => {
  it("dedups by task id, keeping the latest data instead of appending a duplicate", async () => {
    const { connectTaskStream, useTasks } = await import("./events");
    connectTaskStream();
    const source = FakeEventSource.instances[0]!;
    const { tasks } = useTasks();

    source.emit("scan.started", task("t1", { progress: 0 }));
    source.emit("scan.progress", task("t1", { progress: 50 }));

    expect(tasks.value).toHaveLength(1);
    expect(tasks.value[0]!.progress).toBe(50);
  });

  it("caps the list at 50, dropping the oldest, newest first", async () => {
    const { connectTaskStream, useTasks } = await import("./events");
    connectTaskStream();
    const source = FakeEventSource.instances[0]!;
    const { tasks } = useTasks();

    for (let i = 0; i < 51; i++) source.emit("scan.done", task(`t${i}`, { status: "done" }));

    expect(tasks.value).toHaveLength(50);
    expect(tasks.value[0]!.id).toBe("t50"); // newest first
    expect(tasks.value.some((t) => t.id === "t0")).toBe(false); // oldest dropped
  });

  it("ignores a malformed message instead of throwing", async () => {
    const { connectTaskStream, useTasks } = await import("./events");
    connectTaskStream();
    const source = FakeEventSource.instances[0]!;
    const { tasks } = useTasks();

    expect(() => source.emitRaw("not json")).not.toThrow();
    expect(tasks.value).toHaveLength(0);
  });
});

describe("onTaskDone / onTaskEvent dispatch", () => {
  it("fires onTaskDone only for .done/.failed events, not .started/.progress", async () => {
    const { connectTaskStream, onTaskDone } = await import("./events");
    connectTaskStream();
    const source = FakeEventSource.instances[0]!;
    const done = vi.fn();
    onTaskDone(done);

    source.emit("scan.started", task("t1"));
    source.emit("scan.progress", task("t1"));
    expect(done).not.toHaveBeenCalled();

    source.emit("scan.done", task("t1", { status: "done" }));
    expect(done).toHaveBeenCalledTimes(1);
    expect(done).toHaveBeenCalledWith(expect.objectContaining({ id: "t1" }));

    source.emit("download.failed", task("t2", { status: "failed" }));
    expect(done).toHaveBeenCalledTimes(2);
  });

  it("fires onTaskEvent for every event, including non-terminal ones", async () => {
    const { connectTaskStream, onTaskEvent } = await import("./events");
    connectTaskStream();
    const source = FakeEventSource.instances[0]!;
    const handler = vi.fn();
    onTaskEvent(handler);

    source.emit("download.progress", task("t1"));
    expect(handler).toHaveBeenCalledWith(
      "download.progress",
      expect.objectContaining({ id: "t1" }),
    );
  });

  it("disposer removes the handler so it stops firing", async () => {
    const { connectTaskStream, onTaskDone } = await import("./events");
    connectTaskStream();
    const source = FakeEventSource.instances[0]!;
    const done = vi.fn();
    const dispose = onTaskDone(done);

    dispose();
    source.emit("scan.done", task("t1", { status: "done" }));
    expect(done).not.toHaveBeenCalled();
  });
});

it("reflects connection gaps, filters running tasks, and disposes event subscribers", async () => {
  const { connectTaskStream, useTasks, onTaskEvent, activeTasks } = await import("./events");
  connectTaskStream();
  const source = FakeEventSource.instances[0]!;
  const state = useTasks();
  source.onopen?.();
  expect(state.connected.value).toBe(true);
  source.onerror?.();
  expect(state.connected.value).toBe(false);
  source.onopen?.();
  expect(state.connected.value).toBe(true);
  const handler = vi.fn();
  const dispose = onTaskEvent(handler);
  source.emit("scan.started", task("a"));
  source.emit("scan.done", task("b", { status: "done" }));
  expect(activeTasks.value.map((t) => t.id)).toEqual(["a"]);
  dispose();
  source.emit("scan.progress", task("a", { progress: 25 }));
  expect(handler).toHaveBeenCalledTimes(2);
  expect(state.tasks.value.find((t) => t.id === "a")?.progress).toBe(25);
});

it("recovers active phases on reconnect without overwriting newer events", async () => {
  let resolveSnapshot!: (value: { data: Task[] }) => void;
  fetchTasks.mockReturnValueOnce(
    new Promise((resolve) => {
      resolveSnapshot = resolve;
    }),
  );
  const { connectTaskStream, activeTasks, useTasks } = await import("./events");
  connectTaskStream();
  const source = FakeEventSource.instances[0]!;
  source.onopen?.();
  source.emit("scan.progress", task("live", { progress: 80 }));
  resolveSnapshot({
    data: [
      task("live", { progress: 20 }),
      task("restored", {
        status: "cancelling",
        phases: { thumbnails: { completed: 3, total: 9 } },
      }),
    ],
  });
  await flushPromises();
  expect(useTasks().tasks.value.find((t) => t.id === "live")?.progress).toBe(80);
  expect(activeTasks.value.find((t) => t.id === "restored")?.phases?.thumbnails?.completed).toBe(3);
  fetchTasks.mockResolvedValueOnce({ data: [task("restored", { status: "cancelled" })] });
  source.onopen?.();
  await flushPromises();
  expect(activeTasks.value.some((t) => t.id === "restored")).toBe(false);
});

it("retains active operations beyond the history cap and reports cancellation as terminal", async () => {
  const { connectTaskStream, activeTasks, onTaskDone } = await import("./events");
  connectTaskStream();
  const source = FakeEventSource.instances[0]!;
  for (let index = 0; index < 55; index++)
    source.emit("scan.started", task(`active-${index}`, { status: "queued" }));
  expect(activeTasks.value).toHaveLength(55);
  const done = vi.fn();
  const dispose = onTaskDone(done);
  source.emit("scan.cancelled", task("active-0", { status: "cancelled" }));
  expect(done).toHaveBeenCalledTimes(1);
  expect(activeTasks.value).toHaveLength(54);
  dispose();
});

it("keeps the stream usable when snapshot fetching fails or returns no data", async () => {
  fetchTasks.mockRejectedValueOnce(new Error("Connection lost"));
  const { connectTaskStream, useTasks } = await import("./events");
  connectTaskStream();
  const source = FakeEventSource.instances[0]!;
  source.onopen?.();
  await flushPromises();
  expect(useTasks().connected.value).toBe(true);
  fetchTasks.mockResolvedValueOnce({});
  source.onopen?.();
  await flushPromises();
  source.emit("scan.progress", task("after-reconnect", { progress: 40 }));
  expect(useTasks().tasks.value[0]?.progress).toBe(40);
});
