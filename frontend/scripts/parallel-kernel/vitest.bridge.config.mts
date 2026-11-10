import { defineConfig } from 'vitest/config';

/** Explicit bridge suite against the sibling 06 worktree. The product suite's
 * normal include is src/**, so this file is never collected by `npm test`. */
export default defineConfig({
  test: {
    include: ['scripts/parallel-kernel/product-session-bridge.test.ts'],
  },
});
