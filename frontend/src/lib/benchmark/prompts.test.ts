import { describe, expect, it } from "vitest";

import {
  adjustCharRatio,
  buildPrompt,
  buildSections,
  promptChars,
  sectionsToPrompt,
} from "./prompts";

describe("benchmark prompts", () => {
  it("emits the canonical section order with room for filler rules", () => {
    const sections = buildSections({ totalTokens: 2048, memoryTokens: 512, nonce: 1 });
    expect(sections.map((section) => section.name)).toEqual([
      "campaign_context",
      "system_state",
      "memory_injection",
      "style_rules",
      "messages",
      "player_action",
    ]);
  });

  it("grows the prompt monotonically across the whole budget range", () => {
    const charsAt = (total: number) =>
      promptChars(buildPrompt({ totalTokens: total, memoryTokens: Math.floor(total / 2), nonce: 1 }));
    // The skeleton must shrink with the budget instead of holding at ~437 chars.
    expect(charsAt(64)).toBeLessThan(charsAt(128));
    expect(charsAt(128)).toBeLessThan(charsAt(512));
    expect(charsAt(512)).toBeLessThan(charsAt(2048));
  });

  it("keeps small budgets near their nominal size", () => {
    // At ratio 1.0 a 64-token prompt must be a few dozen chars past the floor,
    // not the old fixed ~437-char skeleton.
    expect(promptChars(buildPrompt({ totalTokens: 64, memoryTokens: 32, nonce: 1 }))).toBeLessThan(140);
    expect(promptChars(buildPrompt({ totalTokens: 128, memoryTokens: 64, nonce: 1 }))).toBeLessThan(200);
  });

  it("scales the memory section with the injection budget", () => {
    const memorySection = (memoryTokens: number) =>
      buildSections({ totalTokens: 2048, memoryTokens, nonce: 3 }).find(
        (section) => section.name === "memory_injection",
      )!;
    expect(promptChars(memorySection(1024).text)).toBeGreaterThan(promptChars(memorySection(256).text) * 2);
  });

  it("produces distinct prompts per nonce so the KV cache cannot hit", () => {
    const first = buildPrompt({ totalTokens: 512, memoryTokens: 256, nonce: 1 });
    const second = buildPrompt({ totalTokens: 512, memoryTokens: 256, nonce: 2 });
    expect(first).not.toEqual(second);
  });

  it("is deterministic for a given seed", () => {
    expect(buildPrompt({ totalTokens: 1024, memoryTokens: 512, nonce: 5 }))
      .toEqual(buildPrompt({ totalTokens: 1024, memoryTokens: 512, nonce: 5 }));
  });

  it("keeps sections joined by blank lines", () => {
    const sections = buildSections({ totalTokens: 256, memoryTokens: 64, nonce: 9 });
    expect(sectionsToPrompt(sections)).toContain("\n\n");
  });

  it("recalibrates chars-per-token toward the measured ratio", () => {
    // Built for 1024 tokens at ratio 1.0, tokenizer counted 800: the prompt
    // had too FEW tokens, so more chars per token are needed.
    expect(adjustCharRatio(1.0, 800, 1024)).toBe(1.28);
    expect(adjustCharRatio(1.0, 1024, 1024)).toBe(1.0);
    // Tokenizer counted 2048 for a 512-token prompt: too many tokens,
    // so the ratio must shrink.
    expect(adjustCharRatio(1.0, 2048, 512)).toBeLessThan(1.0);
  });

  it("clamps the calibrated ratio to a sane band", () => {
    expect(adjustCharRatio(1.0, 10, 2048)).toBe(4.0);
    expect(adjustCharRatio(1.0, 100000, 256)).toBe(0.5);
    expect(adjustCharRatio(1.0, 0, 512)).toBe(1.0);
  });
});
