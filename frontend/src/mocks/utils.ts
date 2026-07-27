// Deterministic helpers for mock data: seeded RNG + date/id helpers. Every
// generator downstream is seeded from a stable string (a series id, index,
// etc.) so the mock library looks the same across reloads instead of
// reshuffling every time the page refreshes.

export function hashSeed(input: string): number {
  let h = 2166136261;
  for (let i = 0; i < input.length; i++) {
    h ^= input.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function mulberry32(seed: number): () => number {
  let a = seed;
  return function random() {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export type Rng = () => number;

export function rngFor(seed: string): Rng {
  return mulberry32(hashSeed(seed));
}

export function pick<T>(rng: Rng, items: readonly T[]): T {
  const item = items[Math.floor(rng() * items.length)];
  if (item === undefined) throw new Error("pick() called with an empty pool");
  return item;
}

export function pickN<T>(rng: Rng, items: readonly T[], n: number): T[] {
  const pool = [...items];
  const out: T[] = [];
  for (let i = 0; i < n && pool.length > 0; i++) {
    const idx = Math.floor(rng() * pool.length);
    out.push(pool.splice(idx, 1)[0] as T);
  }
  return out;
}

export function randInt(rng: Rng, min: number, max: number): number {
  return Math.floor(rng() * (max - min + 1)) + min;
}

export function chance(rng: Rng, probability: number): boolean {
  return rng() < probability;
}

/** Pick from a weighted pool: [[weight, value], ...]. Weights need not sum to 1. */
export function weighted<T>(rng: Rng, pool: ReadonlyArray<readonly [number, T]>): T {
  const total = pool.reduce((sum, [w]) => sum + w, 0);
  let roll = rng() * total;
  for (const [w, value] of pool) {
    roll -= w;
    if (roll <= 0) return value;
  }
  const last = pool[pool.length - 1];
  if (!last) throw new Error("weighted() called with an empty pool");
  return last[1];
}

const NOW = Date.now();

export function daysAgo(n: number): string {
  return new Date(NOW - n * 86_400_000).toISOString();
}
export function hoursAgo(n: number): string {
  return new Date(NOW - n * 3_600_000).toISOString();
}
export function minutesAgo(n: number): string {
  return new Date(NOW - n * 60_000).toISOString();
}
export function nowIso(): string {
  return new Date(NOW).toISOString();
}

export function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "");
}

/** Base64url-ish opaque cursor — the real API's cursor is an encoded keyset,
 *  but any string that round-trips through the query param is fine here. */
export function encodeCursor(offset: number): string {
  return btoa(`offset:${offset}`);
}
export function decodeCursorOffset(cursor: string | null | undefined): number {
  if (!cursor) return 0;
  try {
    const decoded = atob(cursor);
    const match = /^offset:(\d+)$/.exec(decoded);
    return match?.[1] ? Number(match[1]) : 0;
  } catch {
    return 0;
  }
}
