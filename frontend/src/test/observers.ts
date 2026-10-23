import { vi } from "vite-plus/test";
export class TestIntersectionObserver {
  static instances: TestIntersectionObserver[] = [];
  observed: Element[] = [];
  disconnect = vi.fn();
  constructor(private callback: IntersectionObserverCallback) {
    TestIntersectionObserver.instances.push(this);
  }
  observe(target: Element) {
    this.observed.push(target);
  }
  unobserve() {}
  emit(visible: boolean) {
    this.callback(
      this.observed.map(
        (target) => ({ target, isIntersecting: visible }) as IntersectionObserverEntry,
      ),
      this as unknown as IntersectionObserver,
    );
  }
  emitEmpty() {
    this.callback([], this as unknown as IntersectionObserver);
  }
}
export class TestResizeObserver {
  static instances: TestResizeObserver[] = [];
  disconnect = vi.fn();
  constructor(private callback: ResizeObserverCallback) {
    TestResizeObserver.instances.push(this);
  }
  observe() {}
  unobserve() {}
  emit() {
    this.callback([], this as unknown as ResizeObserver);
  }
}
export function installObservers() {
  TestIntersectionObserver.instances = [];
  TestResizeObserver.instances = [];
  vi.stubGlobal("IntersectionObserver", TestIntersectionObserver);
  vi.stubGlobal("ResizeObserver", TestResizeObserver);
  vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(300);
  vi.spyOn(HTMLElement.prototype, "scrollWidth", "get").mockReturnValue(600);
}
