import type { NextConfig } from "next";
import path from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = path.dirname(fileURLToPath(import.meta.url));

const nextConfig: NextConfig = {
  outputFileTracingRoot: frontendRoot,
  // Dev and a production build must not share the same output directory: a
  // `next build` rewrites the manifests a running `next dev` is serving, which
  // turns every route into 500/PageNotFound. Acceptance builds set
  // NEXT_DIST_DIR=.next-prod and start from the same value.
  distDir: process.env.NEXT_DIST_DIR ?? '.next',
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
      // The product page runs wllama in the browser. Without these headers
      // crossOriginIsolated is false and the engine falls back to one thread,
      // which makes every six-stage prompt slow enough to look like a semantic
      // timeout. 09 checks crossOriginIsolated===true before a real run.
      { source: "/world-local", headers: isolation },
      { source: "/world-local/:path*", headers: isolation },
    ];
  },
};

export default nextConfig;
