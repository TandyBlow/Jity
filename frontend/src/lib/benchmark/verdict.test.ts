import { describe, expect, it } from "vitest";

import { judgeAccept } from "./verdict";

describe("4s acceptance verdict", () => {
  it("does not rate a short output as within target even when the reason is length", () => {
    // Regression: llama.cpp reports "length" for context-exhaustion stops
    // too, so the reason string cannot prove the requested load was
    // delivered. Requested 512, got 1, reason "length" → not rated.
    const verdict = judgeAccept(
      { predictedTokens: 1, finishReason: "length", wallMs: 100 },
      512,
      4000,
    );
    expect(verdict.completedLoad).toBe(false);
    expect(verdict.withinTarget).toBeUndefined();
  });

  it("rates a completed load within the target", () => {
    const verdict = judgeAccept(
      { predictedTokens: 512, finishReason: "length", wallMs: 3500 },
      512,
      4000,
    );
    expect(verdict.completedLoad).toBe(true);
    expect(verdict.withinTarget).toBe(true);
  });

  it("fails a completed load over the target", () => {
    const verdict = judgeAccept(
      { predictedTokens: 512, finishReason: "length", wallMs: 4500 },
      512,
      4000,
    );
    expect(verdict.completedLoad).toBe(true);
    expect(verdict.withinTarget).toBe(false);
  });

  it("never rates an errored run", () => {
    const verdict = judgeAccept(
      { error: "用户停止", predictedTokens: 512, finishReason: "length", wallMs: 100 },
      512,
      4000,
    );
    expect(verdict.completedLoad).toBe(false);
    expect(verdict.withinTarget).toBeUndefined();
  });
});
