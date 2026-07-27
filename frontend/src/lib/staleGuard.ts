// Guards an async load against out-of-order responses: if the user navigates/filters
// again before an in-flight request resolves, the older response must not overwrite
// state a newer request already populated. Each call site takes a token before
// starting its async work and checks it's still current before applying the result.

export interface StaleGuard {
  /** Call before starting a new load; invalidates any load already in flight. */
  next(): number;
  /** Call with the token from `next()` after the async work resolves. */
  isCurrent(token: number): boolean;
}

export function createStaleGuard(): StaleGuard {
  let current = 0;
  return {
    next: () => ++current,
    isCurrent: (token: number) => token === current,
  };
}
