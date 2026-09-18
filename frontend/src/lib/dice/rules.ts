export type Outcome = "critical" | "success" | "failure" | "fumble";

export type CheckDifficulty = "容易" | "普通" | "困难" | "极难";

export type CheckSpec = {
  name: string;
  skill: string;
  system: string;
  expression: string;
  target: number;
  difficulty: CheckDifficulty;
  stakes: string;
};

export type CheckSeed = Omit<CheckSpec, "expression">;

export function checkExpression(spec: { target: number }): string {
  return `1d20 ≥ ${spec.target}`;
}

/**
 * Builds a check spec from the seed values, deriving the display string from
 * the target the server already resolved out of the difficulty band.
 */
export function defineCheck(seed: CheckSeed): CheckSpec {
  return { ...seed, expression: checkExpression(seed) };
}

/**
 * Resolves the roll-high d20 rules.
 *
 * Every check is `1d20 >= target`, so natural 20 is the best face and natural 1
 * the worst.
 */
export function getOutcome(roll: number, spec: CheckSpec): { outcome: Outcome; degree: string } {
  if (roll === 20) return { outcome: "critical", degree: "大成功" };
  if (roll === 1) return { outcome: "fumble", degree: "大失败" };
  if (roll < spec.target) return { outcome: "failure", degree: "失败" };
  return { outcome: "success", degree: "成功" };
}
