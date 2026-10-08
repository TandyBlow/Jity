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

  it("skips the filler rules section when the fixed sections already cover the budget", () => {
    const sections = buildSections({ totalTokens: 256, memoryTokens: 64, nonce: 1 });
    expect(sections.map((section) => section.name)).not.toContain("style_rules");
    expect(sections.map((section) => section.name)).toEqual([
      "campaign_context",
      "system_state",
      "memory_injection",
      "messages",
      "player_action",
    ]);
  });

  it("grows the prompt monotonically with the token budget", () => {
    const small = promptChars(buildPrompt({ totalTokens: 512, memoryTokens: 256, nonce: 1 }));
    const large = promptChars(buildPrompt({ totalTokens: 2048, memoryTokens: 512, nonce: 1 }));
    expect(large).toBeGreaterThan(small * 2);
  });

  it("scales the memory section with the injection budget", () => {
    const sections = (memoryTokens: number) =>
      buildSections({ totalTokens: 2048, memoryTokens, nonce: 3 }).find(
        (section) => section.name === "memory_injection",
      )!;
    expect(promptChars(sections(1024).text)).toBeGreaterThan(promptChars(sections(256).text) * 2);
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
