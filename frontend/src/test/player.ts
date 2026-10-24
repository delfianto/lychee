import { vi } from "vite-plus/test";
export class TestPlayer {
  static instances: TestPlayer[] = [];
  handlers = new Map<string, () => void>();
  play = vi.fn().mockResolvedValue(undefined);
  // Match Plyr's DOM ownership: wrap the element, then restore a clone on destroy.
  // A no-op destroy misses bugs where Vue patches the detached original video.
  readonly container: HTMLDivElement;
  readonly original: HTMLVideoElement;
  destroy = vi.fn(() => this.container.replaceWith(this.original));
  off = vi.fn((event: string) => this.handlers.delete(event));
  on(event: string, handler: () => void) {
    this.handlers.set(event, handler);
  }
  constructor(
    readonly element: HTMLVideoElement,
    readonly options: Record<string, unknown>,
  ) {
    this.original = element.cloneNode(true) as HTMLVideoElement;
    this.container = document.createElement("div");
    this.container.className = "plyr";
    element.replaceWith(this.container);
    this.container.append(element);
    TestPlayer.instances.push(this);
  }
  emit(event: string) {
    this.handlers.get(event)?.();
  }
}
