import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { relativeTime } from "./format";

const NOW = new Date("2026-01-15T12:00:00.000Z");

describe("relativeTime", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  function ago(ms: number): string {
    return new Date(NOW.getTime() - ms).toISOString();
  }
  function fromNow(ms: number): string {
    return new Date(NOW.getTime() + ms).toISOString();
  }

  it("formats seconds in the past", () => {
    expect(relativeTime(ago(30 * 1000))).toBe("30 seconds ago");
  });

  it("formats minutes, hours, days, weeks, months, and years in the past", () => {
    expect(relativeTime(ago(5 * 60 * 1000))).toBe("5 minutes ago");
    expect(relativeTime(ago(3 * 3600 * 1000))).toBe("3 hours ago");
    expect(relativeTime(ago(2 * 86400 * 1000))).toBe("2 days ago");
    expect(relativeTime(ago(3 * 604800 * 1000))).toBe("3 weeks ago");
    expect(relativeTime(ago(2 * 2592000 * 1000))).toBe("2 months ago");
    expect(relativeTime(ago(2 * 31536000 * 1000))).toBe("2 years ago");
  });

  it("formats future timestamps (e.g. a scheduled/clock-skewed date)", () => {
    expect(relativeTime(fromNow(5 * 60 * 1000))).toBe("in 5 minutes");
  });

  it("uses Intl's 'now' phrasing for a timestamp within the same second", () => {
    expect(relativeTime(NOW.toISOString())).toBe("now");
  });
});
