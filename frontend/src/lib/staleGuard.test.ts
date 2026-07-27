import { describe, expect, it } from "vitest";

import { createStaleGuard } from "./staleGuard";

describe("createStaleGuard", () => {
  it("a token is current until a newer one is issued", () => {
    const guard = createStaleGuard();
    const a = guard.next();
    expect(guard.isCurrent(a)).toBe(true);

    const b = guard.next();
    expect(guard.isCurrent(a)).toBe(false); // a is now stale
    expect(guard.isCurrent(b)).toBe(true);
  });

  it("resolving out of order still only the latest token reads as current", () => {
    const guard = createStaleGuard();
    const first = guard.next();
    const second = guard.next();
    const third = guard.next();

    // Simulate the first-issued request resolving last.
    expect(guard.isCurrent(third)).toBe(true);
    expect(guard.isCurrent(second)).toBe(false);
    expect(guard.isCurrent(first)).toBe(false);
  });
});
