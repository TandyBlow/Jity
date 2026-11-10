/** Prompt assembly for the instruct candidate.
 *
 * One system turn states the writing contract; one user turn carries the
 * scene. A short program-made content plan orders the beats without spending
 * another model call. Nothing here is persisted or treated as state: the
 * verifier grades the draft against the committed facts, not against this
 * text.
 */
import type { CandidateIssueKind, InstructCandidatePolicy, SceneProjection } from './types';

export const DEFAULT_SYSTEM_PROMPT = [
  '你是一位中文小说作者。读者只能看到你写的正文。',
  '写作规则：',
  '1. 用第三人称写一个连贯的场景，两段左右，约 {target} 字（不少于 {min} 字）；不要标题、编号、括号说明、总结或作者旁白。',
  '2. 【本次变化】里的每一条都必须写出来，可以换说法、换顺序。',
  '3. 只用资料里出现的人名、地名、物品和细节。资料没写的不要补：不要新增人物、往事、线索、承诺、物品或战果。',
  '4. 主角做了什么由资料给定；可以一笔带过，但不要整句照抄，也不要给主角加别的动作，不要替任何角色宣布行动成功或失败。',
  '5. 只写主角能看到、听到的事；叙述里不要用“我”自称。主角的心里话可以写，别人的心理不要写，只写他们外在的动作、表情和说话。',
  '6. 语言具体、克制，短句为主，不堆形容词。没有变化时写一小段此刻的静止场面，不要逐项介绍人物和物品。',
].join('\n');

export interface PromptParts { system: string; user: string }

/** Explicit newline constant: the template literals in this file are built by
 * concatenation so the source never depends on editor escape handling. */
const NEWLINE = String.fromCharCode(10);

/** The player's committed action is third-person background. Leaving “我” in
 * the prompt makes a small model continue in first person (run-1 S1 did), so
 * the pronoun is replaced outside quotes; dialogue keeps what the player said. */
export function thirdPersonAction(action: string, name: string): string {
  let quoted = false;
  let out = '';
  for (const char of action) {
    if (char === '“' || char === '「') quoted = true;
    else if (char === '”' || char === '」') quoted = false;
    out += !quoted && char === '我' ? name : char;
  }
  return out;
}

function plan(projection: SceneProjection): string[] {
  const steps: string[] = [];
  if (projection.place.name) steps.push('先交代此刻在哪、什么时候：' + projection.place.name + '，' + projection.time);
  if (projection.playerAction) steps.push('主角刚做完「' + thirdPersonAction(projection.playerAction, projection.viewpoint.name) + '」，从这里接下去');
  const changes = projection.facts.filter((fact) => fact.mandatory);
  // The plan names the KIND of beat, not the fact sentence again: repeating
  // the full sentence here made a 1.5B model narrate the same walk twice.
  if (changes.some((fact) => fact.kind === 'moved')) steps.push('把这段移动写成一个连续动作，只写一次');
  if (changes.some((fact) => fact.kind === 'item_moved')) steps.push('交代物品到了谁手里，用动作带出来');
  if (changes.some((fact) => fact.kind === 'task_achieved')) steps.push('写到他做成了这件事，用结果本身，不要写“完成任务”');
  if (changes.some((fact) => !['moved', 'task_achieved', 'item_moved', 'time'].includes(fact.kind))) steps.push('写出其余变化，写成看得见的神色或动作');
  if (changes.some((fact) => fact.kind === 'time')) steps.push('用环境或动作带出时间流逝，不要写“时间过去”');
  steps.push('停在当前这一刻，不写下一步计划，不写结果评价');
  return steps;
}

function characterLine(entry: SceneProjection['characters'][number]): string {
  const role = entry.viewpoint ? '主角，视角' : '在场';
  const parts = [`- ${entry.name}（${role}）`];
  if (entry.appearance) parts.push(entry.appearance);
  if (entry.personality) parts.push(entry.personality);
  if (entry.carrying.length) parts.push(`随身：${entry.carrying.join('、')}`);
  return parts.join('；');
}

export function buildSceneUserPrompt(projection: SceneProjection, policy: InstructCandidatePolicy): string {
  const lines: string[] = [];
  const facts: string[] = [];
  if (projection.facts.length) {
    facts.push('【本段必须写到】');
    for (const fact of projection.facts) facts.push('- ' + fact.statement + (fact.mandatory ? '' : '（可选）'));
  }
  lines.push('【时间】' + (projection.time || '（未给出）'));
  lines.push('【地点】' + projection.place.name + (projection.place.appearance ? '：' + projection.place.appearance : ''));
  if (projection.place.notes.length) lines.push('【现场】' + projection.place.notes.join('；'));
  // Scene-first variants put the required changes before the cast so the
  // model cannot treat them as an afterthought; the default keeps the
  // place→people→objects→changes order.
  if (policy.variant === 'scene-first') lines.push(...facts);
  if (projection.positions.length) {
    lines.push('【此刻站位】（已经如此，不必逐条复述）');
    for (const entry of projection.positions) lines.push('- ' + entry.name + '在' + entry.location + '。');
  }
  if (projection.characters.length) {
    lines.push('【在场人物】');
    for (const entry of projection.characters.slice(0, 4)) lines.push(characterLine(entry));
  }
  if (projection.items.length) {
    lines.push('【身边可见的东西】');
    for (const item of projection.items.slice(0, 5)) {
      lines.push('- ' + item.name + (item.placement ? '（在' + item.placement + '）' : '') + (item.appearance ? '：' + item.appearance : ''));
    }
  }
  if (policy.variant !== 'scene-first') lines.push(...facts);
  if (projection.playerAction) lines.push('【主角刚才做了什么】' + thirdPersonAction(projection.playerAction, projection.viewpoint.name));
  if (projection.recentEvents.length) lines.push('【刚发生的事】' + projection.recentEvents.join('；'));
  if (projection.priorExcerpt) lines.push('【上一段正文的结尾】' + projection.priorExcerpt);
  if (policy.scene?.previousAction && !projection.playerAction) lines.push('【之前】' + policy.scene.previousAction);
  if (policy.variant !== 'scene-first') {
    const steps = plan(projection).map((step, index) => (index + 1) + '. ' + step).join(NEWLINE);
    lines.push('【写作顺序】' + NEWLINE + steps);
  }
  if (policy.styleSample) {
    lines.push('【风格参考】（只学语气和句子节奏，其中的人名、地点、事件一律不得写进正文）' + NEWLINE + policy.styleSample);
  }
  lines.push('【开始】直接写正文，写满两段，不要解释。');
  return lines.join(NEWLINE);
}

export function buildSystemPrompt(policy: InstructCandidatePolicy): string {
  const target = policy.targetChars ?? 260;
  const base = policy.systemPrompt ?? DEFAULT_SYSTEM_PROMPT;
  return base.replace('{target}', String(target)).replace('{min}', String(policy.minChars ?? 150));
}

const ISSUE_TEXT: Record<string, string> = {
  actor_swap: '把一件事写到了错误的人身上',
  direction_reversed: '移动方向写反了',
  wrong_number: '数字写错了',
  task_claimed_without_fact: '写了没有依据的“完成任务”',
  movement_without_fact: '写了没有依据的移动',
  state_claim_without_fact: '写了没有依据的站位',
  wrong_time: '时间长度写错了',
  added_event: '写了资料里没有的动作事件',
  empty_narration: '没有写出正文',
  fact_omitted: '漏掉了必须写的变化',
  too_short: '太短，没有形成场景',
  too_long: '太长，收不住',
  truncated: '话说到一半断了',
  prompt_echo: '把写作要求或资料标题抄进了正文',
  instruction_echo: '把规则说明写进了正文',
  thinking_leaked: '把思考过程写进了正文',
  not_prose: '写成了列表或提纲，不是小说正文',
  empty_output: '没有输出',
  unlicensed_entity: '写了资料里没有的名字',
  time_missing: '没有写出时间流逝',
  echo_prior: '和上一段正文重复太多',
  first_person_narrator: '用“我”当叙述者写了旁白',
  licensed_event: '',
  cancelled: '', timeout: '', engine_error: '', deadline_exceeded: '',
};

/** Attempt-2 prompt: keep the scene, name the concrete failures, forbid the
 * same mistake. The rejected draft is shown so the model can repair it instead
 * of starting from nothing; evidence keeps the exact text either way. */
export function buildRepairPrompt(args: {
  projection: SceneProjection;
  policy: InstructCandidatePolicy;
  previousText: string;
  issues: { kind: CandidateIssueKind; detail: string; sentence?: string }[];
}): string {
  const problems = args.issues
    .filter((issue) => ISSUE_TEXT[issue.kind])
    .slice(0, 6)
    .map((issue, index) => `${index + 1}) ${ISSUE_TEXT[issue.kind]}${issue.sentence ? `：「${issue.sentence.slice(0, 60)}」` : ''}`);
  return [
    buildSceneUserPrompt(args.projection, args.policy),
    '',
    '【上一次没有通过检查，重写】',
    '【问题】',
    ...(problems.length ? problems : ['1) 正文与资料不一致']),
    '【重写要求】换一种写法，删掉没有依据的内容，把漏掉的变化补上；不要解释，只输出正文。',
  ].join('\n');
}
