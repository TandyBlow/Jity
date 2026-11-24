import { defineCheck, getOutcome, type CheckSpec, type Outcome } from "@/lib/dice/rules";
import type { StoryOptionCheck, StoryOutput } from "@/types";

export type CheckRoll = { roll: number; outcome: Outcome; degree: string };

export function toCheckSpec(metadata: StoryOptionCheck): CheckSpec | null {
  if (metadata.requires_check === false) return null;

  // The server resolves the target out of the difficulty band before the
  // payload is ever built, so the number here is never the model's own.
  return defineCheck({
    name: metadata.name ?? "行动检定",
    skill: metadata.skill ?? "行动",
    system: metadata.system ?? "通用 d20",
    target: metadata.target ?? 12,
    difficulty: metadata.difficulty ?? "普通",
    stakes: metadata.stakes ?? "成功会推进当前行动，失败会带来相应后果。",
  });
}

export function resolveOptionCheck(output: StoryOutput, optionIndex: number): CheckSpec | null {
  const metadata = output.option_checks?.[optionIndex];
  return metadata ? toCheckSpec(metadata) : null;
}

/** Result colour bucket, matching the overlay's revealed-state styling. */
export function outcomeTone(outcome: Outcome): "critical" | "success" | "failure" {
  if (outcome === "critical") return "critical";
  if (outcome === "success") return "success";
  return "failure";
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
