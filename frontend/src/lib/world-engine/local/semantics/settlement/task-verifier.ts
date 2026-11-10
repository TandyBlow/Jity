/** Second-layer task check: a settled fact citation is still only a pointer.
 * This call asks whether the cited fact actually satisfies the task goal
 * condition; attempts, partial progress and copied goal text must not pass.
 * It is an in-pipeline semantic judgement, not a keyword rule. */
import type { EntityDelta, Id, WorldState } from '../../../types';
import type { InferenceEngine } from '../../../runtime/engine';
import type { SettlementOptions } from './types';
import type { ModelCallEvidence } from './types';
import { callJson } from './engine-call';
import { asRecord, asString, isRecord, resultFacts, taskIndex, toJson } from './support';

export interface TaskSupport {
  characterId: Id;
  taskId: Id;
  basis: string;
}

export interface VerifierVerdict {
  characterId: Id;
  taskId: Id;
  satisfied: 'yes' | 'no' | 'partial';
  reason: string;
}

export interface VerifierContext {
  engine: InferenceEngine;
  state: WorldState;
  results: Record<Id, string>;
  options: SettlementOptions;
}

export interface VerifierResult {
  judgments: VerifierVerdict[];
  raw: string;
  ms: number;
  calls: ModelCallEvidence[];
}

const VERIFIER_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['judgments'],
  properties: {
    judgments: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['characterId', 'taskId', 'satisfied', 'reason'],
        properties: {
          characterId: { type: 'string' },
          taskId: { type: 'string' },
          satisfied: { enum: ['yes', 'no', 'partial'] },
          reason: { type: 'string' },
        },
      },
    },
  },
};

export async function verifyTaskAchievements(
  ctx: VerifierContext,
  supports: TaskSupport[],
): Promise<VerifierResult> {
  const facts = resultFacts(ctx.results);
  const byFact = new Map(facts.map((fact) => [fact.id, fact]));
  const index = taskIndex(ctx.state);
  const lines = supports.map((support) => {
    const row = index.get(support.taskId);
    const goal = row?.task.goal ?? support.taskId;
    const owner = ctx.state.initial.characters[support.characterId]?.name ?? support.characterId;
    const fact = support.basis === 'time'
      ? `依据：当前世界时间是 ${ctx.state.time.dateTime}`
      : `依据 ${support.basis}：${byFact.get(support.basis)?.text ?? '（引用不存在）'}`;
    return `- ${owner}（${support.characterId}）任务 ${support.taskId}：${goal}\n  ${fact}`;
  });
  const prompt = [
    '你是中文跑团游戏的任务条件核验器。只输出 JSON，不要解释。',
    '任务目标是一个必须被事实完整满足的条件。对下面每条判断：给出的依据是否已经让该条件成立？',
    '只有依据本身已经让条件成立才判 yes。部分完成、尝试、接近、只提到相关人物、只复述目标、时间只是过去（除非目标本身就是时间条件）都判 no 或 partial。',
    '依据是其他人物的行动也可以，但必须真的让该任务条件成立。',
    '任务：',
    ...lines,
    `输出 {"judgments":[{"characterId":"${supports[0]?.characterId ?? 'lu'}","taskId":"${supports[0]?.taskId ?? 't1'}","satisfied":"yes|no|partial","reason":"一句话"}]}（每条一行，不能多也不能少）。`,
  ].join('\n');
  const answer = await callJson(ctx.engine, prompt, {
    maxTokens: 520,
    temperature: ctx.options.temperature ?? 0,
    timeoutMs: ctx.options.timeoutMs,
    maxPromptChars: ctx.options.maxPromptChars,
    jsonSchema: VERIFIER_SCHEMA,
    validate: (value) => readVerifierJudgments(value, supports),
  });
  const judgments = readVerifierJudgments(answer.value, supports);
  return { judgments, raw: answer.raw, ms: answer.ms, calls: answer.calls };
}

export function readVerifierJudgments(value: unknown, supports: TaskSupport[]): VerifierVerdict[] {
  const rows = asRecord(value).judgments;
  if (!Array.isArray(rows)) throw new Error('verifier judgments must be an array');
  const expected = new Set(supports.map((row) => `${row.characterId}:${row.taskId}`));
  const seen = new Set<string>();
  const out: VerifierVerdict[] = [];
  for (const raw of rows) {
    if (!isRecord(raw)) throw new Error('verifier judgment must be an object');
    const characterId = asString(raw.characterId);
    const taskId = asString(raw.taskId);
    const key = `${characterId}:${taskId}`;
    if (!expected.has(key)) throw new Error(`verifier judged an undeclared achievement: ${key}`);
    if (seen.has(key)) throw new Error(`verifier judged twice: ${key}`);
    seen.add(key);
    const satisfied = asString(raw.satisfied);
    if (satisfied !== 'yes' && satisfied !== 'no' && satisfied !== 'partial') {
      throw new Error(`verifier verdict must be yes/no/partial for ${key}`);
    }
    out.push({ characterId, taskId, satisfied, reason: asString(raw.reason) });
  }
  if (seen.size !== expected.size) {
    throw new Error(`verifier coverage incomplete: ${seen.size}/${expected.size}`);
  }
  return out;
}

/** Keep only subtasks whose parent task was accepted by the verifier. A
 * rejected achievement must not leave its follow-up goal behind. */
export function filterSubtasksByAccepted(
  subtasks: Record<Id, Partial<EntityDelta>>,
  accepted: Record<Id, Partial<EntityDelta>>,
): Record<Id, Partial<EntityDelta>> {
  const acceptedIds = new Set(Object.values(accepted).flatMap((delta) => delta.tasksAchieved ?? []));
  const out: Record<Id, Partial<EntityDelta>> = {};
  for (const [ownerId, delta] of Object.entries(subtasks)) {
    const kept = (delta.subtasksAdded ?? []).filter((task) => !task.parentTaskId || acceptedIds.has(task.parentTaskId));
    if (kept.length) out[ownerId] = { ...delta, subtasksAdded: kept };
  }
  return out;
}
