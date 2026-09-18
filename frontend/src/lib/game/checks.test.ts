import { describe, expect, it } from "vitest";

import { formatActionWithCheckResult, outcomeTone, resolveOptionCheck, rollCheck, seededRoll, toCheckSpec } from "./checks";
import type { StoryOutput } from "@/types";

describe("toCheckSpec", () => {
  it("drops checks the model marked as not required", () => {
    expect(toCheckSpec({ requires_check: false })).toBeNull();
  });

  it("derives a hard threshold from the skill value", () => {
    const spec = toCheckSpec({ normal_target: 12, difficulty: "困难" });

    expect(spec?.target).toBe(6);
    expect(spec?.expression).toBe("1d20 ≤ 6");
  });

  it("falls back to a normal check threshold", () => {
    const spec = toCheckSpec({ normal_target: 14 });

    expect(spec?.target).toBe(14);
  });
});

describe("resolveOptionCheck", () => {
  const output = {
    options: ["查看抽屉", "离开"],
    option_checks: [null, { requires_check: true, normal_target: 10, difficulty: "困难" }],
  } as unknown as StoryOutput;

  it("reads the check attached to the chosen option", () => {
    expect(resolveOptionCheck(output, 1)?.target).toBe(5);
  });

  it("returns null when the option has no check", () => {
    expect(resolveOptionCheck(output, 0)).toBeNull();
  });
});

describe("rollCheck", () => {
  it("reports a failure above the hard threshold", () => {
    const spec = toCheckSpec({ normal_target: 12, difficulty: "困难" });
    const result = rollCheck(spec!, 9);

    expect(result.outcome).toBe("failure");
    expect(result.roll).toBe(9);
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

describe("formatActionWithCheckResult", () => {
  it("appends the roll so the narrator sees the outcome", () => {
    const spec = toCheckSpec({ normal_target: 12 })!;
    const text = formatActionWithCheckResult("查看抽屉", spec, rollCheck(spec, 11));

    expect(text).toContain("查看抽屉");
    expect(text).toContain("[行动判定]");
    expect(text).toContain("骰面 11/20");
  });
});
