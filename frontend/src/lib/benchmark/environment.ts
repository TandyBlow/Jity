import type { EnvironmentInfo, HeapSample, MemorySample } from "./types";

/**
 * WebAssembly feature-detection modules. Each byte array is a minimal valid
 * module that only decodes when the feature is present, so WebAssembly.validate
 * answers the feature question directly. The arrays are unit-tested in
 * environment.test.ts — both had off-by-one section sizes once, which makes
 * the probe silently return false everywhere.
 *
 * threads: type (i32)->i32, a SHARED memory, and i32.atomic.load. Atomics are
 * only valid on shared memory under the threads proposal, so the same module
 * with a plain memory fails to validate (used as the negative control).
 */
const SIMD_DETECT = new Uint8Array([
  0, 97, 115, 109, 1, 0, 0, 0, 1, 5, 1, 96, 0, 1, 123, 3, 2, 1, 0, 10, 10, 1,
  8, 0, 65, 0, 253, 15, 253, 98, 11,
]);
const THREADS_DETECT = new Uint8Array([
  0, 97, 115, 109, 1, 0, 0, 0,
  1, 6, 1, 0x60, 1, 0x7f, 1, 0x7f, // type (i32) -> i32
  3, 2, 1, 0, // func 0
  5, 4, 1, 3, 1, 1, // memory: shared, min 1, max 1
  10, 10, 1, 8, 0, 0x20, 0, 0xfe, 0x10, 2, 0, 0x0b, // body: local.get 0; i32.atomic.load 2 0
]);

export function detectWasmSimd(): boolean {
  return WebAssembly.validate(SIMD_DETECT);
}

export function detectWasmThreads(): boolean {
  return WebAssembly.validate(THREADS_DETECT) && typeof SharedArrayBuffer !== "undefined";
}

export function collectEnvironment(): EnvironmentInfo {
  const nav = navigator as Navigator & { deviceMemory?: number };
  return {
    userAgent: nav.userAgent,
    platform: nav.platform ?? "",
    hardwareConcurrency: nav.hardwareConcurrency ?? null,
    deviceMemoryGB: nav.deviceMemory ?? null,
    crossOriginIsolated: window.crossOriginIsolated === true,
    webgpuExposed: "gpu" in nav,
    wasmSimd: detectWasmSimd(),
    wasmThreadsPossible: detectWasmThreads(),
    collectedAt: new Date().toISOString(),
  };
}

type ChromeMemory = {
  usedJSHeapSize: number;
  totalJSHeapSize: number;
};

function chromeMemory(): ChromeMemory | null {
  return (performance as Performance & { memory?: ChromeMemory }).memory ?? null;
}

/** JS heap usage, Chrome only; nulls elsewhere. Sync fallback. */
export function sampleHeap(): HeapSample {
  const memory = chromeMemory();
  if (!memory) return { usedMB: null, totalMB: null };
  return {
    usedMB: Math.round((memory.usedJSHeapSize / 1048576) * 10) / 10,
    totalMB: Math.round((memory.totalJSHeapSize / 1048576) * 10) / 10,
  };
}

type SpecificMemoryResult = {
  bytes: number;
  breakdown: Array<{
    bytes: number;
    types: string[];
  }>;
};

function summarizeBreakdown(
  breakdown: SpecificMemoryResult["breakdown"],
): Record<string, number> {
  const totals: Record<string, number> = {};
  for (const entry of breakdown) {
    const key = entry.types?.join("+") || "other";
    totals[key] = (totals[key] ?? 0) + Math.round(entry.bytes / 1048576);
  }
  return totals;
}

/**
 * Full-page memory including WebAssembly heaps, when the browser exposes the
 * precise API (crossOriginIsolated Chrome). Falls back to the JS-heap-only
 * sample; the caller must treat a missing preciseMB as "unknown", never as
 * evidence that the model does not fit the device.
 */
export async function sampleMemory(): Promise<MemorySample> {
  const precise = (
    performance as Performance & {
      measureUserAgentSpecificMemory?: () => Promise<SpecificMemoryResult>;
    }
  ).measureUserAgentSpecificMemory;
  if (typeof precise === "function") {
    try {
      const result = await precise.call(performance);
      return {
        ...sampleHeap(),
        preciseMB: Math.round((result.bytes / 1048576) * 10) / 10,
        breakdownMB: summarizeBreakdown(result.breakdown ?? []),
      };
    } catch {
      // Some browsers expose the function but reject without isolation.
    }
  }
  return sampleHeap();
}
