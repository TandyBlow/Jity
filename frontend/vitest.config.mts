import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

export default defineConfig({
  // Next preserves JSX for its own compiler; component tests must transform it.
  oxc: { jsx: { runtime: "automatic" } },
  test: {
    // Scoped to src/: e2e/*.spec.ts belongs to Playwright, and vitest's default
    // glob would otherwise collect it and fail on the Playwright test() call.
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
  },
  resolve: {
    // Mirrors the "@/*" path alias in tsconfig.json.
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
});
