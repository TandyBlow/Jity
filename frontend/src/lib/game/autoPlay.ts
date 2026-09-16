import type { GameState } from "@/types";

const PROGRESSION_WEIGHTS: Record<string, number> = {
  推进: 12, 继续: 10, 前往: 10, 进入: 9, 调查: 9, 询问: 8,
  确认: 7, 检查: 7, 追问: 7, 观察: 6, 打开: 6, 寻找: 6,
  跟随: 6, 接受: 5, 任务: 5, 线索: 5,
};

const PASSIVE_WEIGHTS: Record<string, number> = {
  等待: -8, 拒绝: -7, 离开: -7, 睡觉: -6, 开玩笑: -4,
  装傻: -4, 沉默: -4, 逃跑: -4, 什么都不做: -10,
};

export function activeGoalsFromState(state: GameState | null): string[] {
  if (!state) return [];
  const goals: string[] = [];
  const currentGoal = state.player_status?.current_goal?.trim();
  if (currentGoal) goals.push(currentGoal);
  for (const quest of state.quests ?? []) {
    const status = (quest.status ?? "").toLowerCase();
    if (["completed", "complete", "done", "已完成", "完成"].includes(status)) continue;
    const objective = (quest.objective || quest.description || "").trim();
    if (objective && !goals.includes(objective)) goals.push(objective);
  }
  return goals;
}

export function chooseGoalAwareOption(
  options: string[],
  goals: string[],
  recent: string[],
  seed: number,
): { action: string; index: number | null; score: number; reason: string } {
  const clean = options.map((option) => option.trim()).filter(Boolean);
  const fallbackGoal = goals[0] || "当前最明确的线索";
  if (!clean.length) {
    return {
      action: `继续推进“${fallbackGoal}”，检查现场线索并询问相关人物下一步该做什么。`,
      index: null,
      score: 0,
      reason: `无可用选项，围绕当前目标“${fallbackGoal}”生成主动行动`,
    };
  }

  const scored = clean.map((action, index) => {
    const goalScore = goalRelevanceScore(action, goals);
    let score = goalScore;
    for (const [keyword, weight] of Object.entries(PROGRESSION_WEIGHTS)) {
      if (action.includes(keyword)) score += weight;
    }
    for (const [keyword, weight] of Object.entries(PASSIVE_WEIGHTS)) {
      if (action.includes(keyword)) score += weight;
    }
    if (recent.includes(action)) score -= 5;
    score += seededJitter(seed + index * 7919);
    return { action, index: index + 1, score, goalScore };
  });
  scored.sort((a, b) => b.score - a.score || a.index - b.index);
  const best = scored[0];
  const reason = best.goalScore > 0
    ? `与当前目标有 ${best.goalScore} 分短语关联，并结合主动推进评分`
    : "未发现直接目标短语，按主动推进与避免重复评分";
  return { action: best.action, index: best.index, score: best.score, reason };
}

function goalRelevanceScore(option: string, goals: string[]): number {
  const normalizedOption = normalize(option);
  let score = 0;
  for (const goal of goals) {
    const normalizedGoal = normalize(goal);
    const phrases = new Set<string>();
    for (const size of [4, 3, 2]) {
      for (let index = 0; index <= normalizedGoal.length - size; index += 1) {
        phrases.add(normalizedGoal.slice(index, index + size));
      }
    }
    let goalScore = 0;
    for (const phrase of phrases) {
      if (normalizedOption.includes(phrase)) goalScore += phrase.length - 1;
    }
    score += Math.min(18, goalScore);
  }
  return score;
}

function normalize(value: string): string {
  return value.toLowerCase().replace(/[^\p{L}\p{N}]/gu, "");
}

function seededJitter(seed: number): number {
  const value = Math.sin(seed) * 10000;
  return Math.floor((value - Math.floor(value)) * 3);
}
