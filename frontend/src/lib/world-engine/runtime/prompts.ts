/** B3 task prompts for the on-device model. The encoder is the first-cut
 * REAL implementation replacing the B2 placeholder: per-task instruction
 * with the exact output contract (matching structured-output.ts — the codec
 * is the authority; the prompt only teaches it), the serialized declared
 * input, and nothing else — deterministic in (task, key, input) so eval
 * replays stay stable. narration and reaction are TEXT tasks: prose
 * instructions only, JSON contracts are a measured quality poison for
 * small-model prose and must not creep back through the prompt. */
import type { ModelTask } from '../schedule';
import type { Json } from '../types';

function updatesContract(input: Json): string {
  if ((input as { stage?: unknown }).stage !== undefined) {
    return `只输出一个 JSON 对象（不要数组）：{"stage":"${String((input as { stage: unknown }).stage)}","changes":{"实体id":{...增量}}}`;
  }
  return '只输出 JSON 数组：[{"stage":"position","changes":{"实体id":{...增量}}}]。stage 只能是 position/appearance/tasks/subtasks/personality/sanity 之一';
}

function workingCharacters(input: Json): string[] {
  const state = (input as { workingState?: { characters?: Record<string, unknown> } }).workingState;
  return state?.characters ? Object.keys(state.characters) : [];
}

/** Batch and split updates get MUTUALLY EXCLUSIVE contracts — a split call
 * must never read a shape-teaching it may obey against the codec. */
const JSON_CONTRACTS: Record<Exclude<ModelTask, 'narration' | 'reaction' | 'updates'>, string> = {
  action: '决定主角是否行动。只输出 JSON：{"kind":"act","text":"一句话行动描述"} 或 {"kind":"skip"}',
  targets: '列出这一行动会牵连的其他在场角色。只输出 JSON：{"targets":[{"targetId":"角色id"}]}；没有目标则 {"targets":[]}。不要输出触发键或骰点参数',
  results: '结算本组每个成员行动的结果。只输出 JSON 对象：{"角色id":"结果描述",...}，至少一条',
  continuation: '判断回合是否结束。只输出 JSON：继续 {"kind":"continue","closedBy":"model","cancelReason":null,"candidateCharacterIds":["角色id"],"nextRoundId":"新回合id"} 或交还 {"kind":"handback","closedBy":"model","cancelReason":null}',
  initial: '根据设定构建世界初始状态。只输出 JSON，字段恰为 engineVersion/schemaVersion/protagonistId/initialTime/locations/items/characters',
  time: '给出下一个点位的时间推进。只输出 JSON：{"boundary":"elapsed","duration":{"amount":秒数...}} 或零时长 {"boundary":"instant","duration":{"amount":0,"unit":"second"}}；unit 是 second/minute/hour/day/month/year 之一',
  pointPlan: '规划本回合的点位序列。只输出 JSON 数组：[{"pointId":"点id","kind":"normal|instant|linked","timeAdvance":{...同时间格式},"actorIds":["角色id"]}]，至少一个点；无行动者用空数组',
};

const TEXT_CONTRACTS: Record<'narration' | 'reaction', string> = {
  narration: '用两到四句中文写出这一点位的叙事正文：把已结算的行动与变化讲成一个连贯片段。只输出正文文字，不要 JSON、不要标题、不要列表。',
  reaction: '用一两句中文写出该角色被牵连时的反应。只输出正文文字，不要 JSON。',
};

/** The context section: the declared call input serialized verbatim. */
function context(task: ModelTask, key: string, input: Json): string {
  const sections = [`调用键: ${key}`];
  if (task === 'updates' && (input as { stage?: unknown }).stage !== undefined) {
    sections.push(`本调用阶段: ${String((input as { stage: unknown }).stage)}`);
  }
  if (task === 'action' || task === 'targets' || task === 'reaction') {
    const actors = workingCharacters(input);
    if (actors.length) sections.push(`在场角色: ${actors.join(', ')}`);
  }
  sections.push(`输入:\n${JSON.stringify(input)}`);
  return sections.join('\n');
}

export function buildTaskPrompt(task: ModelTask, key: string, input: Json): string {
  if (task === 'narration' || task === 'reaction') {
    return `[任务: ${task}]\n${TEXT_CONTRACTS[task]}\n${context(task, key, input)}\n正文:`;
  }
  const contract = task === 'updates' ? updatesContract(input) : JSON_CONTRACTS[task];
  return `[任务: ${task}]\n${contract}\n${context(task, key, input)}\n输出:`;
}
