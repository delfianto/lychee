// Live task stream (Server-Sent Events). One shared EventSource per app; views
// read `activeTasks` for live progress and register `onTaskDone` to refetch when
// a scan/download finishes. The dev server proxies /api → the backend, so
// `EventSource("/api/events")` is same-origin.

import { computed, readonly, ref } from "vue";

import type { components } from "./schema";
import { api } from "./client";

export type Task = components["schemas"]["TaskOut"];

interface TaskEvent {
  event: string; // "<kind>.started" | ".progress" | ".done" | ".failed"
  task?: Task;
}
type DoneHandler = (task: Task) => void;
type EventHandler = (event: string, task: Task) => void;

const KEEP = 50;
const tasks = ref<Task[]>([]);
let revision = 0;
const revisions = new Map<string, number>();
const connected = ref(false);
const doneHandlers = new Set<DoneHandler>();
const eventHandlers = new Set<EventHandler>();
let source: EventSource | null = null;
export const activity = ref<components["schemas"]["ActivityOut"] | null>(null);
let activityRequest: Promise<void> | null = null;
let activityDirty = false;
let activityTimer: ReturnType<typeof setTimeout> | null = null;
const ACTIVE = ["queued", "running", "cancelling"];
const TERMINAL = ["done", "failed", "cancelled"];

/** Coalesce bursts of unit changes and reject counts made stale by a newer event. */
export function refreshActivity(): Promise<void> {
  activityDirty = true;
  if (activityRequest) return activityRequest;
  activityRequest = (async () => {
    try {
      do {
        activityDirty = false;
        const { data } = await api.GET("/api/activity");
        if (data && !activityDirty) activity.value = data;
      } while (activityDirty);
    } catch {
      // Retain the last count during a connection gap; reconnect/focus retries.
    } finally {
      activityRequest = null;
    }
  })();
  return activityRequest;
}

function scheduleActivityRefresh(): void {
  if (activityTimer !== null) return;
  activityTimer = setTimeout(() => {
    activityTimer = null;
    void refreshActivity();
  }, 100);
}

function upsert(task: Task): boolean {
  revisions.set(task.id, ++revision);
  const at = tasks.value.findIndex((t) => t.id === task.id);
  if (at >= 0 && TERMINAL.includes(tasks.value[at]!.status) && ACTIVE.includes(task.status))
    return false;
  if (at >= 0) tasks.value[at] = task;
  else tasks.value = [task, ...tasks.value];
  let finished = 0;
  tasks.value = tasks.value.filter(
    (item) => ["queued", "running", "cancelling"].includes(item.status) || ++finished <= KEEP,
  );
  const retained = new Set(tasks.value.map((item) => item.id));
  for (const id of revisions.keys()) if (!retained.has(id)) revisions.delete(id);
  return true;
}

/** Seed accepted operations immediately; an SSE update always wins over its HTTP response. */
export function rememberTask(value: unknown): void {
  const task = value as Task | undefined;
  if (!task?.id || !task.kind || !task.status || tasks.value.some((t) => t.id === task.id)) return;
  upsert(task);
  for (const handler of eventHandlers) handler(`${task.kind}.started`, task);
}

/** Reconcile connection gaps without replacing events that arrived during the request. */
export async function refreshTasks(): Promise<void> {
  const requestedAt = revision;
  try {
    const { data } = await api.GET("/api/tasks");
    if (!data) return;
    const present = new Set(data.map((task) => task.id));
    tasks.value = tasks.value.filter(
      (task) => present.has(task.id) || revisions.get(task.id)! > requestedAt,
    );
    for (const task of data) {
      if ((revisions.get(task.id) ?? 0) > requestedAt) continue;
      const previous = tasks.value.find((t) => t.id === task.id);
      if (!upsert(task)) continue;
      for (const handler of eventHandlers) handler(`${task.kind}.snapshot`, task);
      if (
        previous &&
        ["queued", "running", "cancelling"].includes(previous.status) &&
        ["done", "failed", "cancelled"].includes(task.status)
      ) {
        for (const handler of doneHandlers) handler(task);
      }
    }
    void refreshActivity();
  } catch {
    // Keep the last known state; the next connection or focus retries the snapshot.
  }
}

/** Open the shared event stream (idempotent). Call once at app start. */
export function connectTaskStream(): void {
  if (source) return;
  // Snapshot before onopen: a proxy or an idle stream must not delay the badge.
  void refreshTasks();
  void refreshActivity();
  source = new EventSource("/api/events");
  window.addEventListener("online", () => {
    void refreshTasks();
  });
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") void refreshTasks();
  });
  source.onopen = () => {
    connected.value = true;
    void refreshTasks();
  };
  source.onerror = () => {
    // EventSource reconnects on its own; just reflect the gap.
    connected.value = false;
    void refreshTasks();
  };
  source.onmessage = (e: MessageEvent<string>) => {
    let payload: TaskEvent;
    try {
      payload = JSON.parse(e.data) as TaskEvent;
    } catch {
      return;
    }
    if (payload?.event === "activity.changed") {
      scheduleActivityRefresh();
      return;
    }
    if (!payload?.task?.id || typeof payload.event !== "string") return;
    if (!upsert(payload.task)) return;
    for (const handler of eventHandlers) handler(payload.event, payload.task);
    if (
      payload.event.endsWith(".done") ||
      payload.event.endsWith(".failed") ||
      payload.event.endsWith(".cancelled")
    ) {
      for (const handler of doneHandlers) handler(payload.task);
    }
    if (!payload.event.endsWith(".progress")) scheduleActivityRefresh();
  };
}

/** Fire `handler` when any task finishes (done or failed). Returns a disposer. */
export function onTaskDone(handler: DoneHandler): () => void {
  doneHandlers.add(handler);
  return () => {
    doneHandlers.delete(handler);
  };
}

/** Fire `handler` for every task event (started/progress/done/failed). Returns a disposer. */
export function onTaskEvent(handler: EventHandler): () => void {
  eventHandlers.add(handler);
  return () => {
    eventHandlers.delete(handler);
  };
}

export const activeTasks = computed(() =>
  tasks.value.filter((t) => ["queued", "running", "cancelling"].includes(t.status)),
);

export function useTasks() {
  return { tasks: readonly(tasks), activeTasks, connected: readonly(connected) };
}
