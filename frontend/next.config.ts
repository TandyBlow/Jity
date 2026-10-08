import type { NextConfig } from "next";
import path from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = path.dirname(fileURLToPath(import.meta.url));

const nextConfig: NextConfig = {
  outputFileTracingRoot: frontendRoot,
  // Cross-origin isolation is required for the multi-threaded wasm runtime on
  // /benchmark (SharedArrayBuffer). Scoped to that path so the game pages are
  // unaffected.
  async headers() {
    return [
      {
        source: "/benchmark",
        headers: [
          { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
          { key: "Cross-Origin-Embedder-Policy", value: "require-corp" },
        ],
      },
    ];
  },
};

export default nextConfig;
