import { vi } from "vite-plus/test";
export class TestPlayer {
  static instances: TestPlayer[] = [];
  handlers = new Map<string, () => void>();
  play = vi.fn().mockResolvedValue(undefined);
  destroy = vi.fn();
  off = vi.fn((event: string) => this.handlers.delete(event));
  on(event: string, handler: () => void) {
    this.handlers.set(event, handler);
  }
  constructor(
    readonly element: HTMLVideoElement,
    readonly options: Record<string, unknown>,
  ) {
    TestPlayer.instances.push(this);
  }
  emit(event: string) {
    this.handlers.get(event)?.();
  }
}
