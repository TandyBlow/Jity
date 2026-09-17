import { describe, expect, it } from "vitest";
import { checkExpression, defineCheck, getOutcome, requiredRoll, type CheckSpec } from "./rules";

function makeCheck(overrides: Partial<Parameters<typeof defineCheck>[0]> = {}): CheckSpec {
  return defineCheck({
    name: "侦查检定",
    skill: "侦查",
    system: "通用 d20",
    normalTarget: 12,
    difficulty: "普通",
    stakes: "测试",
    ...overrides,
  });
}

const ordinaryCheck = makeCheck();
const hardCheck = makeCheck({ difficulty: "困难" });

describe("roll-under d20 outcome", () => {
  it("treats natural 1 as critical success and natural 20 as fumble", () => {
    expect(getOutcome(1, ordinaryCheck)).toEqual({ outcome: "critical", degree: "大成功" });
    expect(getOutcome(20, ordinaryCheck)).toEqual({ outcome: "fumble", degree: "大失败" });
  });

  it("uses the target as an inclusive success boundary", () => {
    expect(getOutcome(12, ordinaryCheck)).toEqual({ outcome: "success", degree: "成功" });
    expect(getOutcome(13, ordinaryCheck)).toEqual({ outcome: "failure", degree: "失败" });
  });

  it("resolves hard and extreme success thresholds", () => {
    expect(getOutcome(2, hardCheck)).toEqual({ outcome: "success", degree: "极难成功" });
    expect(getOutcome(6, hardCheck)).toEqual({ outcome: "success", degree: "困难成功" });
  });
});

describe("difficulty raises the required roll", () => {
  it("halves the threshold for a hard check", () => {
    expect(requiredRoll(ordinaryCheck)).toBe(12);
    expect(requiredRoll(hardCheck)).toBe(6);
  });

  it("derives target and expression from normalTarget and difficulty", () => {
    expect(hardCheck.target).toBe(6);
    expect(checkExpression(hardCheck)).toBe("1d20 ≤ 6");
    expect(checkExpression(ordinaryCheck)).toBe("1d20 ≤ 12");
  });

  it("fails a hard check on rolls that a normal check would pass", () => {
    expect(getOutcome(9, ordinaryCheck).outcome).toBe("success");
    expect(getOutcome(9, hardCheck)).toEqual({ outcome: "failure", degree: "失败" });
  });
});
