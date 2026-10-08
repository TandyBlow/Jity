import { describe, expect, it } from "vitest";

import { detectWasmSimd, detectWasmThreads } from "./environment";

describe("wasm feature detection", () => {
  it("validates the SIMD probe module", () => {
    // Node (and every shipping browser) supports SIMD, so the probe must
    // decode. An off-by-one section size makes it silently false everywhere.
    expect(detectWasmSimd()).toBe(true);
  });

  it("validates the threads probe module", () => {
    // The probe is a shared memory + i32.atomic.load module; Node supports
    // threads, so it must validate. This caught a real bug: a wrong section
    // size made the probe undecodable and reported "no threads" everywhere.
    expect(detectWasmThreads()).toBe(true);
  });

  it("reports no threads when SharedArrayBuffer is unavailable", () => {
    // Multi-threaded wasm needs SharedArrayBuffer regardless of what the
    // module probe says. There is no usable byte-level negative control:
    // modern engines validate atomics on plain memory too, so a plain-memory
    // variant does not distinguish anything.
    const original = globalThis.SharedArrayBuffer;
    delete (globalThis as { SharedArrayBuffer?: unknown }).SharedArrayBuffer;
    try {
      expect(detectWasmThreads()).toBe(false);
    } finally {
      if (original) globalThis.SharedArrayBuffer = original;
    }
  });
});
