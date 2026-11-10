/** Prompt composition WITHOUT a second fact serializer.
 *
 * The caller/lane-01 serialization (`inputText`) is the model input. This file
 * only inserts an optional task instruction, the scene-mode writing contract,
 * the previous draft (revise mode) and the grounded repair guidance directly
 * BEFORE the body marker, so the head of the serialized string keeps its
 * trained shape. If the caller wants different placement,
 * `policy.composePrompt` replaces this entirely.
 */
import type { ComposePromptArgs, NarrationPolicy } from './types';

const BODY_MARKERS = ['【正文】', '\n正文：', '\n正文:', '【叙事】'] as const;

const clampInt = (value: number, min: number, max: number): number =>
  Math.min(max, Math.max(min, Math.round(Number.isFinite(value) ? value : min)));

/** The last body marker wins: a serialized input may contain the word 正文 in
 * an earlier field, and the model continues from the final one. */
function bodyMarkerIndex(inputText: string): number {
  let best = -1;
  for (const marker of BODY_MARKERS) {
    const index = inputText.lastIndexOf(marker);
    if (index > best) best = index;
  }
  return best;
}

export function insertBeforeBody(inputText: string, block: string): string {
  if (!block.trim()) return inputText;
  const index = bodyMarkerIndex(inputText);
  if (index < 0) return `${inputText}\n${block}`;
  const head = inputText.slice(0, index);
  const tail = inputText.slice(index);
  const before = head.length === 0 || head.endsWith('\n') ? '' : '\n';
  const after = tail.startsWith('\n') ? '' : '\n';
  return `${head}${before}${block}${after}${tail}`;
}

/** The writing contract for whole-scene mode.
 *
 * The serialized input already contains every settled fact, but it is shaped
 * as a state record, and an instruct model asked to continue it does three
 * things the product rejected in real runs: it invents connective events
 * (footsteps, a gun in the wrong hand), it repeats the state labels, and it
 * ends on a stock closing line that comes back every turn. The contract names
 * those failures explicitly. It adds no fact and removes no fact: every
 * sentence it demands is in the caller's serialization.
 *
 * Pronoun rule: the world file carries no gender field and the serialization
 * rarely states one, so a 1.7B instruct model guessed wrong («她» for 路明非)
 * in accepted product prose. Writing names or dropping the subject is correct
 * Chinese and cannot be wrong about gender. */
export function writingContract(policy: NarrationPolicy): string {
  const view = policy.viewpoint?.name;
  const target = clampInt(policy.targetChars ?? 240, 60, 600);
  return [
    '【写法】',
    `第三人称，只写${view ? `${view}看得见、听得见的东西` : '主角看得见、听得见的东西'}；写成一个连贯的短场景，约${target}字，可分两到三段。`,
    '只写上面已经结算的内容：不要新增人物、物品、地点、事件、往事、承诺或数字。',
    '只写上面写过的声音、气味和物件；没写过的脚步声、枪声、风声、气味、心跳都不要补。',
    '称呼人物时用名字或省略主语，不要用他/她指代人物，避免写错性别。',
    '名字是「某人物的某物」的东西只属于那个人，不要把它写到别人手里。',
    '不要写上面没有给出的姿势（蹲下、坐下、靠墙、站起），人物保持原本的姿态。',
    '不要把状态清单念一遍：不写“精神值”“未完成”“任务”“视角”这些字样，用动作、环境和对话表现。',
    '不要写「完成了一项任务」「个性发生了变化」「新增一条待办」这类报告句式，把结果写进动作或对话里。',
    '时间推进要落在一句话里（例如“十分钟过去”），不要写日期，不要写别的时长。',
    '结尾停在这一刻，不要总结、不要“这一天就这样过去”这类收束，最后一句要与上一回合的结尾不同。',
    '不写标题，不解释写法，直接写正文。',
  ].join('\n');
}

export function composeNarrationPrompt(args: ComposePromptArgs, policy: NarrationPolicy): string {
  if (policy.composePrompt) return policy.composePrompt(args);
  const blocks: string[] = [];
  if (args.instruction?.trim()) blocks.push(args.instruction.trim());
  // Whole-scene mode gets the contract by default; beat mode builds its own
  // per-beat prompt (see beats.ts) and never comes through here.
  if (policy.mode !== 'beats' && policy.writingContract !== false && !args.previousDraft?.trim()) {
    blocks.push(writingContract(policy));
  }
  if (args.previousDraft?.trim()) {
    blocks.push(['【上一稿】', args.previousDraft.trim(), '【修订要求】'].join('\n'));
  }
  if (args.guidance.trim()) blocks.push(args.guidance.trim());
  return insertBeforeBody(args.inputText, blocks.join('\n\n'));
}
