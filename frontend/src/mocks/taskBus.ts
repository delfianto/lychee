// A tiny in-memory pub/sub standing in for the backend's task queue + SSE
// broadcast. `simulateTask` fires started → progress (×N) → done/failed on a
// timer and every `/api/events` connection (see handlers.ts) forwards those
// same events to the browser, so scan/sync/download/match all drive real
// progress bars and toasts instead of resolving instantly.

import type { components } from "../api/schema";

type TaskOut = components["schemas"]["TaskOut"];

interface TaskEvent {
  event: string; // "<kind>.started" | ".progress" | ".done" | ".failed"
  task: TaskOut;
}

type Listener = (payload: TaskEvent) => void;
const listeners = new Set<Listener>();

export function subscribeTaskStream(fn: Listener): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

function emit(event: string, task: TaskOut): void {
  for (const fn of listeners) fn({ event, task: { ...task } });
}

let counter = 0;
function nextTaskId(): string {
  counter += 1;
  return `task-${counter}-${Date.now()}`;
}

export interface SimulateTaskOptions {
  kind: string;
  label: string;
  /** Number of progress ticks between "started" and "done" (default 4). */
  steps?: number;
  stepDelayMs?: number;
  /** Progress percentage (1-99) at which the task fails instead of completing; omit to always succeed. */
  failAt?: number;
  detailForStep?: (step: number, progress: number) => string | undefined;
  failureDetail?: string;
  result?: Record<string, unknown>;
  onProgress?: (task: TaskOut) => void;
  onDone?: (task: TaskOut) => void;
  onFailed?: (task: TaskOut) => void;
}

/** Kick off a fire-and-forget task simulation; returns the initial (running,
 *  0%) TaskOut synchronously so a POST handler can answer with 202 right away. */
export function simulateTask(opts: SimulateTaskOptions): TaskOut {
  const task: TaskOut = {
    id: nextTaskId(),
    kind: opts.kind,
    label: opts.label,
    status: "running",
    progress: 0,
    detail: null,
    result: null,
  };
  const steps = Math.max(1, opts.steps ?? 4);
  const stepDelay = opts.stepDelayMs ?? 450;

  emit(`${opts.kind}.started`, task);

  let step = 0;
  const tick = (): void => {
    step += 1;
    task.progress = Math.min(99, Math.round((step / steps) * 100));
    task.detail = opts.detailForStep?.(step, task.progress) ?? task.detail;

    if (opts.failAt != null && task.progress >= opts.failAt) {
      task.status = "failed";
      task.detail = opts.failureDetail ?? task.detail ?? "Task failed.";
      emit(`${opts.kind}.failed`, task);
      opts.onFailed?.(task);
      return;
    }

    emit(`${opts.kind}.progress`, task);
    opts.onProgress?.(task);

    if (step < steps) {
      setTimeout(tick, stepDelay);
    } else {
      task.status = "done";
      task.progress = 100;
      task.result = opts.result ?? null;
      emit(`${opts.kind}.done`, task);
      opts.onDone?.(task);
    }
  };
  setTimeout(tick, stepDelay);

  return task;
}
