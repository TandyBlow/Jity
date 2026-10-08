import type { EnvironmentInfo, HeapSample } from "./types";

/**
 * WebAssembly feature-detection payloads. A module that validates true for
 * these byte strings means the browser supports the feature (same technique
 * as the wasm-feature-detect package).
 */
const SIMD_DETECT = new Uint8Array([
  0, 97, 115, 109, 1, 0, 0, 0, 1, 5, 1, 96, 0, 1, 123, 3, 2, 1, 0, 10, 10, 1,
  8, 0, 65, 0, 253, 15, 253, 98, 11,
]);
const THREADS_DETECT = new Uint8Array([
  0, 97, 115, 109, 1, 0, 0, 0, 1, 6, 1, 96, 1, 127, 1, 127, 3, 2, 1, 0, 10, 8,
  1, 6, 0, 65, 0, 254, 16, 11,
]);

export function collectEnvironment(): EnvironmentInfo {
  const nav = navigator as Navigator & { deviceMemory?: number };
  return {
    userAgent: nav.userAgent,
    platform: nav.platform ?? "",
    hardwareConcurrency: nav.hardwareConcurrency ?? null,
    deviceMemoryGB: nav.deviceMemory ?? null,
    crossOriginIsolated: window.crossOriginIsolated === true,
    webgpuExposed: "gpu" in nav,
    wasmSimd: WebAssembly.validate(SIMD_DETECT),
    wasmThreadsPossible:
      WebAssembly.validate(THREADS_DETECT) && typeof SharedArrayBuffer !== "undefined",
    collectedAt: new Date().toISOString(),
  };
}

type ChromeMemory = {
  usedJSHeapSize: number;
  totalJSHeapSize: number;
};

/**
 * JS heap usage. Chrome-only; other browsers return nulls. This does not
 * include the wasm linear memory of the model itself, so the exported record
 * treats it as advisory context, not an absolute footprint.
 */
export function sampleHeap(): HeapSample {
  const memory = (performance as Performance & { memory?: ChromeMemory }).memory;
  if (!memory) return { usedMB: null, totalMB: null };
  return {
    usedMB: Math.round((memory.usedJSHeapSize / 1048576) * 10) / 10,
    totalMB: Math.round((memory.totalJSHeapSize / 1048576) * 10) / 10,
  };
}
