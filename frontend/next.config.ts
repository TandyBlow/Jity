import type { NextConfig } from "next";
import path from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = path.dirname(fileURLToPath(import.meta.url));

const nextConfig: NextConfig = {
  outputFileTracingRoot: frontendRoot,
  // Cross-origin isolation is required for the multi-threaded wasm runtime
  // (SharedArrayBuffer): /benchmark for the inference benchmarks and /world
  // for the page's narration model — single-threaded prompt eval measured
  // ~200ms/token, which no deadline can absorb. Game pages stay unaffected.
  async headers() {
    const isolation = [
      { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
      { key: "Cross-Origin-Embedder-Policy", value: "require-corp" },
    ];
    return [
      { source: "/benchmark", headers: isolation },
      { source: "/world", headers: isolation },
    ];
  },
};

export default nextConfig;
