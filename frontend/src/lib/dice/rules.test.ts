import { describe, expect, it } from "vitest";
import { checkExpression, defineCheck, getOutcome, type CheckSpec } from "./rules";

function makeCheck(overrides: Partial<Parameters<typeof defineCheck>[0]> = {}): CheckSpec {
  return defineCheck({
    name: "侦查检定",
    skill: "侦查",
    system: "通用 d20",
    target: 12,
    difficulty: "普通",
    stakes: "测试",
    ...overrides,
  });
}

const ordinaryCheck = makeCheck();
const hardCheck = makeCheck({ target: 16, difficulty: "困难" });

describe("roll-high d20 outcome", () => {
  it("treats natural 20 as critical success and natural 1 as fumble", () => {
    expect(getOutcome(20, ordinaryCheck)).toEqual({ outcome: "critical", degree: "大成功" });
    expect(getOutcome(1, ordinaryCheck)).toEqual({ outcome: "fumble", degree: "大失败" });
  });

  it("uses the target as an inclusive success boundary", () => {
    expect(getOutcome(12, ordinaryCheck)).toEqual({ outcome: "success", degree: "成功" });
    expect(getOutcome(11, ordinaryCheck)).toEqual({ outcome: "failure", degree: "失败" });
  });

  it("fails a hard check on a roll the ordinary check would pass", () => {
    expect(getOutcome(12, ordinaryCheck).outcome).toBe("success");
    expect(getOutcome(12, hardCheck)).toEqual({ outcome: "failure", degree: "失败" });
  });
});

describe("the displayed expression follows the target", () => {
  it("renders the roll-high threshold", () => {
    expect(checkExpression(ordinaryCheck)).toBe("1d20 ≥ 12");
    expect(checkExpression(hardCheck)).toBe("1d20 ≥ 16");
  });
});
