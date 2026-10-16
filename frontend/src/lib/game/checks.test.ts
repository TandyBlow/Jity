import { describe, expect, it } from "vitest";

import { outcomeTone, resolveOptionCheck, rollCheck, seededRoll, toActionCheckSubmission, toCheckSpec } from "./checks";
import type { StoryOutput } from "@/types";

describe("toCheckSpec", () => {
  it("drops checks the model marked as not required", () => {
    expect(toCheckSpec({ requires_check: false })).toBeNull();
  });

  it("uses the target the server derived from the difficulty band", () => {
    const spec = toCheckSpec({ target: 16, difficulty: "困难" });

    expect(spec?.target).toBe(16);
    expect(spec?.expression).toBe("1d20 ≥ 16");
  });

  it("falls back to an ordinary check", () => {
    expect(toCheckSpec({})?.target).toBe(12);
  });
});

describe("resolveOptionCheck", () => {
  const output = {
    options: ["查看抽屉", "离开"],
    option_checks: [null, { requires_check: true, target: 16, difficulty: "困难" }],
  } as unknown as StoryOutput;

  it("reads the check attached to the chosen option", () => {
    expect(resolveOptionCheck(output, 1)?.target).toBe(16);
  });

  it("returns null when the option has no check", () => {
    expect(resolveOptionCheck(output, 0)).toBeNull();
  });
});

describe("rollCheck", () => {
  it("reports a failure below the hard threshold", () => {
    const spec = toCheckSpec({ target: 16, difficulty: "困难" });
    const result = rollCheck(spec!, 9);

    expect(result.outcome).toBe("failure");
    expect(result.roll).toBe(9);
  });

  it("reports a success at or above it", () => {
    const spec = toCheckSpec({ target: 16, difficulty: "困难" });

    expect(rollCheck(spec!, 16).outcome).toBe("success");
  });
});

describe("outcomeTone", () => {
  it("maps each outcome onto the overlay's result colours", () => {
    expect(outcomeTone("critical")).toBe("critical");
    expect(outcomeTone("success")).toBe("success");
    expect(outcomeTone("failure")).toBe("failure");
    expect(outcomeTone("fumble")).toBe("failure");
  });
});

describe("seededRoll", () => {
  it("stays inside 1..20 and repeats for the same seed", () => {
    for (let seed = 0; seed < 200; seed += 1) {
      const roll = seededRoll(seed);
      expect(roll).toBeGreaterThanOrEqual(1);
      expect(roll).toBeLessThanOrEqual(20);
      expect(seededRoll(seed)).toBe(roll);
    }
  });
});

describe("toActionCheckSubmission", () => {
  it("preserves the zero-based index, including the first option", () => {
    expect(toActionCheckSubmission(11, 0)).toEqual({ roll: 11, option_index: 0 });
    expect(toActionCheckSubmission(20, 2)).toEqual({ roll: 20, option_index: 2 });
  });

  it("omits the option index for a custom action", () => {
    expect(toActionCheckSubmission(1, null)).toEqual({ roll: 1 });
    expect(toActionCheckSubmission(12)).toEqual({ roll: 12 });
  });
});
