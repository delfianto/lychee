// Live task stream (Server-Sent Events). One shared EventSource per app; views
// read `activeTasks` for live progress and register `onTaskDone` to refetch when
// a scan/download finishes. The dev server proxies /api → the backend, so
// `EventSource("/api/events")` is same-origin.

import { computed, readonly, ref } from "vue";

import type { components } from "./schema";

export type Task = components["schemas"]["TaskOut"];

interface TaskEvent {
  event: string; // "<kind>.started" | ".progress" | ".done" | ".failed"
  task: Task;
}
type DoneHandler = (task: Task) => void;

const KEEP = 50;
const tasks = ref<Task[]>([]);
const connected = ref(false);
const doneHandlers = new Set<DoneHandler>();
let source: EventSource | null = null;

function upsert(task: Task): void {
  const at = tasks.value.findIndex((t) => t.id === task.id);
  if (at >= 0) tasks.value[at] = task;
  else tasks.value = [task, ...tasks.value].slice(0, KEEP);
}

/** Open the shared event stream (idempotent). Call once at app start. */
export function connectTaskStream(): void {
  if (source) return;
  source = new EventSource("/api/events");
  source.onopen = () => {
    connected.value = true;
  };
  source.onerror = () => {
    // EventSource reconnects on its own; just reflect the gap.
    connected.value = false;
  };
  source.onmessage = (e: MessageEvent<string>) => {
    let payload: TaskEvent;
    try {
      payload = JSON.parse(e.data) as TaskEvent;
    } catch {
      return;
    }
    upsert(payload.task);
    if (payload.event.endsWith(".done") || payload.event.endsWith(".failed")) {
      for (const handler of doneHandlers) handler(payload.task);
    }
  };
}

/** Fire `handler` when any task finishes (done or failed). Returns a disposer. */
export function onTaskDone(handler: DoneHandler): () => void {
  doneHandlers.add(handler);
  return () => {
    doneHandlers.delete(handler);
  };
}

export const activeTasks = computed(() => tasks.value.filter((t) => t.status === "running"));

export function useTasks() {
  return { tasks: readonly(tasks), activeTasks, connected: readonly(connected) };
}
