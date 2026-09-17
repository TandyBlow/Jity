import { defineCheck, getOutcome, type CheckSpec, type Outcome } from "@/components/dice-demo/dice-rules";
import type { StoryOptionCheck, StoryOutput } from "@/types";

export type CheckRoll = { roll: number; outcome: Outcome; degree: string };

export function toCheckSpec(metadata: StoryOptionCheck): CheckSpec | null {
  if (metadata.requires_check === false) return null;

  // The payload's own target is ignored: difficulty and the skill value decide
  // the threshold, so a hard check cannot advertise a normal success rate.
  return defineCheck({
    name: metadata.name ?? "行动检定",
    skill: metadata.skill ?? "行动",
    system: metadata.system ?? "通用 d20",
    normalTarget: metadata.normal_target ?? metadata.target ?? 12,
    difficulty: metadata.difficulty ?? "普通",
    stakes: metadata.stakes ?? "成功会推进当前行动，失败会带来相应后果。",
  });
}

export function resolveOptionCheck(output: StoryOutput, optionIndex: number): CheckSpec | null {
  const metadata = output.option_checks?.[optionIndex];
  return metadata ? toCheckSpec(metadata) : null;
}

export function rollCheck(check: CheckSpec, roll: number): CheckRoll {
  const evaluation = getOutcome(roll, check);
  return { roll, outcome: evaluation.outcome, degree: evaluation.degree };
}

/** Deterministic d20 so auto-play runs stay reproducible. */
export function seededRoll(seed: number): number {
  const value = Math.sin(seed) * 10000;
  return Math.floor((value - Math.floor(value)) * 20) + 1;
}

export function formatActionWithCheckResult(action: string, check: CheckSpec, result: CheckRoll): string {
  return `${action}\n\n[行动判定] ${check.system} ${check.expression}，骰面 ${result.roll}/20，${result.degree}。`;
}
