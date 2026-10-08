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

  it("rejects the non-shared-memory negative control", () => {
    // Atomics on a plain memory are invalid under the threads proposal; if
    // this module ever validates, the probe is not actually testing threads.
    const nonShared = new Uint8Array([
      0, 97, 115, 109, 1, 0, 0, 0,
      1, 6, 1, 0x60, 1, 0x7f, 1, 0x7f,
      3, 2, 1, 0,
      5, 4, 1, 1, 1, // plain memory (flags 0x01)
      10, 10, 1, 8, 0, 0x20, 0, 0xfe, 0x10, 2, 0, 0x0b,
    ]);
    expect(WebAssembly.validate(nonShared)).toBe(false);
  });
});
