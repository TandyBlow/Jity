import type { NextConfig } from "next";
import path from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = path.dirname(fileURLToPath(import.meta.url));

const nextConfig: NextConfig = {
  outputFileTracingRoot: frontendRoot,
  // Cross-origin isolation is required for the multi-threaded wasm runtime on
  // /benchmark (SharedArrayBuffer). Scoped to that path so the game pages are
  // unaffected.
  // Dev proxy to the local narration service: the page never talks to the
  // service host directly, and the world protocol stays untouched.
  async rewrites() {
    return [
      {
        source: "/narration-api/:path*",
        destination: "http://127.0.0.1:8031/:path*",
      },
    ];
  },
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
