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
import { projectTaskInput } from './focused-input';
import type { CommittedRead } from './committed-narration';

function updatesContract(input: Json): string {
  const confirmed = (input as { results?: unknown }).results !== undefined ? 'results 是结算描述，文本本身不是执行事实；这里只生成待核对候选，权威更新必须由规则凭据产生。' : '';
  const stageFields: Record<string, string> = {
    position: 'positionSet={containerId,slotId:null,relativeTo:null}', appearance: 'appearanceChanges=[{id,text,supersedes:[]}]',
    tasks: 'tasksAchieved=[任务id]', subtasks: 'subtasksAdded=[{id,ownerId,parentTaskId,goal,status}]',
    personality: 'personalityChanges=[{id,text,supersedes:[]}]', sanity: 'sanitySet=数值',
  };
  const stage = (input as { stage?: string }).stage;
  const fields = `增量字段：${stage ? stageFields[stage] : Object.entries(stageFields).map(([key, field]) => `${key}→${field}`).join('；')}。只写本阶段已确认发生变化的实体；未变化用 changes={}，不要添加事实。`;
  if ((input as { stage?: unknown }).stage !== undefined) {
    return `${confirmed}只输出一个 JSON 对象（不要数组）：{"stage":"${String((input as { stage: unknown }).stage)}","changes":{"实体id":{...增量}}}。${fields}`;
  }
  return `${confirmed}只输出 JSON 数组：[{"stage":"position","changes":{"实体id":{...增量}}}]。stage 只能是 position/appearance/tasks/subtasks/personality/sanity 之一。${fields}`;
}

function workingCharacters(input: Json): string[] {
  const state = (input as { workingState?: { characters?: Record<string, unknown> } }).workingState;
  return state?.characters ? Object.keys(state.characters) : [];
}

/** Batch and split updates get MUTUALLY EXCLUSIVE contracts — a split call
 * must never read a shape-teaching it may obey against the codec. */
const JSON_CONTRACTS: Record<Exclude<ModelTask, 'narration' | 'reaction' | 'updates'>, string> = {
  action: '判断输入 actor 指定的角色此刻是否行动（不一定是主角）。advance 给出玩家输入与消费状态：仅当该角色是主角且 intentStatus 为 pending 时，它是待处理命令，必须结合最新工作状态判断能否执行——目标或条件已失效则不可执行；consumed 时它已是触发背景，不得重复执行；其他角色按自身任务与个性判断。只输出 JSON：{"kind":"act","text":"一句话行动描述"} 或 {"kind":"skip"}',
  targets: '列出这一行动会牵连的其他在场角色。只输出 JSON：{"targets":[{"targetId":"角色id"}]}；没有目标则 {"targets":[]}。不要输出触发键或骰点参数',
  results: '结算本组每个成员行动的结果。members 给出全组冻结行动与全部骰点判定（含未准入），结果必须与这些行动和判定一致。只输出 JSON 对象：{"角色id":"结果描述",...}，至少一条',
  continuation: '判断回合是否结束。输入含当前世界 workingState（主角在其中）与本轮已提交变化 roundChanges。只输出 JSON：继续 {"kind":"continue","closedBy":"model","cancelReason":null,"candidateCharacterIds":["角色id"],"nextRoundId":"新回合id"} 或交还 {"kind":"handback","closedBy":"model","cancelReason":null}',
  initial: '根据设定构建世界初始状态。只输出 JSON，字段恰为 engineVersion/schemaVersion/protagonistId/initialTime/locations/items/characters',
  time: '给出下一个点位的时间推进。只输出 JSON：{"boundary":"elapsed","duration":{"amount":秒数...}} 或零时长 {"boundary":"instant","duration":{"amount":0,"unit":"second"}}；unit 是 second/minute/hour/day/month/year 之一',
  pointPlan: '规划本回合的点位序列。actorIds 声明本点覆盖的冻结槽位（点位切分），每个被列出的槽位都会单独判断行动（act/skip）；未列出的槽位不得被当作跳过。只输出 JSON 数组：[{"pointId":"点id","kind":"normal|instant|linked","timeAdvance":{...同时间格式},"actorIds":["角色id"]}]，至少一个点；无行动者用空数组',
};

const TEXT_CONTRACTS: Record<'narration' | 'reaction', string> = {
  narration: '用两句中文、不超过80字写出这一点位的叙事正文：只表达 before/变化 delta/after 中的事实，人物动作归属不得互换，不补写新事件或物品。只输出正文文字，不要 JSON、不要标题、不要列表。',
  reaction: '用一两句中文写出该角色被牵连时的反应：必须针对输入 sourceActionText 里的具体威胁。只输出正文文字，不要 JSON。',
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
  if (task === 'action') {
    const actor = (input as { actor?: string }).actor;
    const state = (input as { workingState?: { protagonistId?: string; initial?: { characters?: Record<string, { name?: string }> } } }).workingState;
    const focused = input as { protagonistId?: string; actorState?: { name?: string } };
    const protagonist = state?.protagonistId ?? focused.protagonistId;
    const name = state?.initial?.characters?.[actor ?? key]?.name ?? focused.actorState?.name ?? actor ?? key;
    sections.push(`本次只判断: ${actor ?? key}（${name}）；主角: ${protagonist ?? '由输入给出'}。行动句写明该角色。${actor === protagonist ? '本角色就是主角，判断待处理命令。' : '本角色不是主角，不得代主角执行玩家命令。'}`);
  }
  sections.push(`输入:\n${JSON.stringify(input)}`);
  return sections.join('\n');
}

export function buildTaskPrompt(task: ModelTask, key: string, input: Json, options: { inputMode?: 'full' | 'focused'; committedReads?: { before: CommittedRead | null; after: CommittedRead } } = {}): string {
  let view = options.inputMode === 'focused' ? projectTaskInput(task, input, options.committedReads) : input;
  if (task === 'narration' && options.committedReads && options.inputMode !== 'focused') {
    // Both comparison arms have the SAME expression facts and instruction.
    // The full arm additionally carries before/delta/after once, not the
    // get_state proof objects a second time.
    const focused = projectTaskInput(task, input, options.committedReads) as Record<string, Json>;
    view = { ...(input as Record<string, Json>), facts: focused.facts };
  }
  if (task === 'narration' || task === 'reaction') {
    // The facts contract applies whenever the view IS (or carries) the
    // focused projection — focused-without-reads passes the projected view
    // directly, and giving it the full-mode prose instruction (which names
    // before/delta/after fields the view does not contain) measurably
    // derails a 0.5B model into listing every allowed phrase instead of
    // picking one per fact.
    const contract = task === 'narration' && (options.committedReads !== undefined || options.inputMode === 'focused')
      ? '只用 facts 中的允许短句组织正文，每条事实表达一次；可换顺序，句间用句号。不要增加、遗漏或修改事实；不要标题、不要 JSON。'
      : TEXT_CONTRACTS[task];
    return `[任务: ${task}]\n${contract}\n${context(task, key, view)}\n正文:`;
  }
  const contract = task === 'updates' ? updatesContract(input) : JSON_CONTRACTS[task];
  return `[任务: ${task}]\n${contract}\n${context(task, key, view)}\n输出:`;
}
