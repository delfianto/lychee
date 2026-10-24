/** Window scroll restoration waits for the returning route and its loaded results. */
export interface BrowsePosition {
  left: number;
  top: number;
}

export function createBrowseScroll() {
  const positions = new Map<string, BrowsePosition>();
  let cancelPending: (() => void) | undefined;

  function cancel(): void {
    cancelPending?.();
  }

  function remember(key: string): void {
    positions.set(key, { left: window.scrollX, top: window.scrollY });
  }

  function restore(
    key: string,
    saved: BrowsePosition | null,
    revisit: boolean,
  ): Promise<BrowsePosition | false> {
    cancel();
    const position = saved ?? (revisit ? positions.get(key) : undefined) ?? { left: 0, top: 0 };
    return new Promise((resolve) => {
      let observer: MutationObserver;
      let timeout: ReturnType<typeof setTimeout>;
      function finish(result: BrowsePosition | false): void {
        observer.disconnect();
        clearTimeout(timeout);
        window.removeEventListener("wheel", cancel);
        window.removeEventListener("touchstart", cancel);
        cancelPending = undefined;
        resolve(result);
      }
      function clamp(): BrowsePosition {
        return {
          left: position.left,
          top: Math.min(
            position.top,
            Math.max(0, document.documentElement.scrollHeight - window.innerHeight),
          ),
        };
      }
      function attempt(): void {
        const page = [...document.querySelectorAll<HTMLElement>("[data-browse-route]")].find(
          (element) => element.dataset.browseRoute === key,
        );
        if (!page) return;
        // Cached grids can refresh after an edit. Wait for the whole retained
        // depth, rather than scrolling against the first cursor page's height.
        if (
          position.top > 0 &&
          (page.hasAttribute("data-browse-loading") || page.querySelector("[data-browse-loading]"))
        )
          return;
        finish(clamp());
      }
      observer = new MutationObserver(attempt);
      observer.observe(document.body, {
        childList: true,
        subtree: true,
        attributes: true,
        attributeFilter: ["data-browse-route", "data-browse-loading"],
      });
      timeout = setTimeout(() => finish(clamp()), 10000);
      cancelPending = () => finish(false);
      window.addEventListener("wheel", cancel, { passive: true });
      window.addEventListener("touchstart", cancel, { passive: true });
      attempt();
    });
  }

  return { remember, restore, cancel };
}
