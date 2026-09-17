export type Outcome = "critical" | "success" | "failure" | "fumble";

export type CheckDifficulty = "普通" | "困难";

export type CheckSpec = {
  name: string;
  skill: string;
  system: string;
  expression: string;
  normalTarget: number;
  target: number;
  difficulty: CheckDifficulty;
  stakes: string;
};

export type CheckSeed = {
  name: string;
  skill: string;
  system: string;
  normalTarget: number;
  difficulty: CheckDifficulty;
  stakes: string;
};

/**
 * Effective success threshold of a check.
 *
 * `normalTarget` is the skill value; difficulty picks which fraction of it
 * counts as success, so a hard check needs a far better roll than a normal one.
 */
export function requiredRoll(spec: CheckSpec): number {
  return spec.difficulty === "困难" ? Math.floor(spec.normalTarget / 2) : spec.normalTarget;
}

export function checkExpression(spec: CheckSpec): string {
  return `1d20 ≤ ${requiredRoll(spec)}`;
}

/**
 * Builds a check spec from the seed values, deriving `target` and `expression`
 * so difficulty stays the single source of truth for the threshold.
 */
export function defineCheck(seed: CheckSeed): CheckSpec {
  const base: CheckSpec = { ...seed, target: seed.normalTarget, expression: "" };
  return { ...base, target: requiredRoll(base), expression: checkExpression(base) };
}

/**
 * Resolves the roll-under d20 rules.
 *
 * Natural 1 is the best result and natural 20 the worst result here because
 * every check is expressed as `1d20 <= target`.
 */
export function getOutcome(roll: number, spec: CheckSpec): { outcome: Outcome; degree: string } {
  if (roll === 1) return { outcome: "critical", degree: "大成功" };
  if (roll === 20) return { outcome: "fumble", degree: "大失败" };
  if (roll > requiredRoll(spec)) return { outcome: "failure", degree: "失败" };
  if (spec.difficulty === "困难" && roll <= Math.floor(spec.normalTarget / 5)) {
    return { outcome: "success", degree: "极难成功" };
  }
  if (spec.difficulty === "困难") return { outcome: "success", degree: "困难成功" };
  return { outcome: "success", degree: "成功" };
}
