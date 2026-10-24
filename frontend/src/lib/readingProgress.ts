/** Coalesce page changes and serialize saves so a slow earlier request cannot win. */
export function createProgressWriter(
  send: (chapterId: string, page: number, completed?: boolean) => Promise<void>,
  status: (error: string | null) => void,
) {
  type Position = { page: number; completed?: boolean };
  const pending = new Map<string, Position>();
  const accepted = new Map<string, Position>();
  let running: Promise<boolean> | null = null;
  const merge = (a: Position, b?: Position): Position => ({
    page: Math.max(a.page, b?.page ?? 0),
    completed: a.completed || b?.completed ? true : undefined,
  });
  async function flush(): Promise<boolean> {
    if (running) return running;
    running = (async () => {
      while (pending.size) {
        const [id, position] = pending.entries().next().value!;
        pending.delete(id);
        try {
          await send(id, position.page, position.completed);
          status(null);
        } catch (error) {
          pending.set(id, merge(position, pending.get(id)));
          status(error instanceof Error ? error.message : "Couldn’t save reading progress");
          return false;
        }
      }
      return true;
    })();
    const saved = await running;
    running = null;
    return saved;
  }
  return {
    record(id: string, page: number, completed?: boolean): void {
      const next = merge({ page, completed }, accepted.get(id));
      const previous = accepted.get(id);
      if (previous && previous.page === next.page && previous.completed === next.completed) return;
      accepted.set(id, next);
      pending.set(id, merge(next, pending.get(id)));
      void flush();
    },
    flush,
    /** Closing a tab cannot await an existing request; keepalive saves remain monotonic server-side. */
    finish(): void {
      for (const [id, position] of pending)
        void send(id, position.page, position.completed).catch(() => {});
    },
  };
}
