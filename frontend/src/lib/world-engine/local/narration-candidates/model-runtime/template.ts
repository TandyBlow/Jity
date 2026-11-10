/** Prompt rendering + model-template handling for the narration candidates.
 *
 * Two rules this module enforces:
 * 1. The model's own template decides the wire format. The adapter never
 *    pastes ChatML tokens into the prompt by hand for a chat model; it hands
 *    the message list to wllama, which applies the GGUF's Jinja template.
 *    `renderFallbackPrompt` exists only for engines without `chat()`.
 * 2. Thinking output never reaches the player. Qwen3 hybrid checkpoints are
 *    loaded with enable_thinking=false, and any residual `...` block is
 *    removed (also while streaming, so the page never flashes it).
 */
import type { CommittedNarration } from '../../../runtime/committed-narration';
import type { TimeAdvance } from '../../../types';
import type { CandidatePolicy, CandidateScene, ChatTurn, ModelSpec } from './types';
import { NARRATOR_SYSTEM_PROMPT, describeCommitted } from './types';
import { mergePositions, projectProseFacts } from './facts';

/** Render the user turn for a committed narration point. Deterministic for a
 * fixed packet + policy, which lets the probe compare models on one input. */
export function renderNarrationUser(
  committed: CommittedNarration,
  inputText: string,
  policy: CandidatePolicy = {},
): string {
  const scene = policy.scene ?? null;
  const lines: string[] = [];
  const viewName = policy.viewpoint?.name ?? null;
  if (viewName) lines.push(`视角人物：${viewName}。`);
  lines.push(...renderScene(scene));
  const projected = projectProseFacts(committed);
  const facts = describeCommitted(projected.packet);
  if (facts.length > 0) {
    lines.push('这一小段时间里发生的事（必须写进正文，不能添加别的事件）：');
    for (const fact of facts) lines.push(`- ${fact}`);
  } else {
    lines.push('这一小段时间里没有实体变化。不要写任何移动、任务达成或新的动作。');
  }
  const time = normalizeTime(policy.time);
  if (time) {
    lines.push(`本回合经过的时间：${time.amount}${timeUnitWord(time.unit)}。正文里要明确写出「${time.amount}${timeUnitWord(time.unit)}」。`);
  }
  const positions = mergePositions(policy.knownPositions, projected.positions);
  if (positions.length > 0) {
    lines.push('此刻的站位（已经如此，不必逐条复述）：');
    for (const entry of positions) lines.push(`- ${entry.name}在${entry.location}。`);
  }
  if (projected.hints.length > 0) {
    lines.push('只能用神态或动作暗示，不要写出数字，也不要照抄原句：');
    for (const hint of projected.hints) lines.push(`- ${hint}`);
  }
  if (policy.priorText) lines.push(`上一点已写正文（延续语气与位置，不要重复其事件）：\n${trim(policy.priorText, 400)}`);
  // The raw serializer string is evidence for the caller, not material for the
  // prose: feeding 【状态】/【变化】 labels to an instruction model invites it to
  // copy the state format instead of writing a scene. Only include it on request.
  if (policy.includeInputText && inputText.trim()) {
    lines.push(`本点输入资料（只作依据，不要逐项复述，不要照抄字段名）：\n${trim(inputText, 1200)}`);
  }
  const target = policy.targetChars;
  const paragraphs = policy.paragraphs ?? 3;
  const length = target
    ? `写成 ${paragraphs} 段，合计 ${Math.max(policy.minChars ?? Math.round(target * 0.75), 1)}～${target} 字。`
    : `写成 ${paragraphs} 段，合计约 180～260 字。`;
  lines.push(`要求：${length}段与段之间空一行，直接给正文，不要小标题，不要解释。`);
  // Length is the failure the first real run actually showed: a 1.7B model
  // stops after two sentences because it thinks the scene is over.
  if (target) lines.push(`写满目标字数再把这一段场景收住，中途不要概括、不要跳跃。`);
  lines.push('用具体的动作、声音和细节推进，不要把「这一小段时间里发生的事」逐条翻译成句子。');
  // The same run invented an unlisted box opening. Banning unlisted
  // interaction is cheaper than one repair call and keeps the fact grader
  // meaningful.
  lines.push('不要新增没有列出的动作：不开箱、不拿取、不使用物品、不写新的对话内容；没有列出的移动也不得发生。');
  lines.push('没有变化的人物可以保持不动，只写视角人物看到、听到、想到的东西。');
  if (policy.instruction) lines.push(`补充要求：${policy.instruction}`);
  if (policy.knownEntities?.length) {
    lines.push(`可用专名：${policy.knownEntities.join('、')}。不得出现名单外的专名。`);
  }
  return lines.join('\n');
}

function renderScene(scene: CandidateScene | null): string[] {
  if (!scene) return [];
  const lines: string[] = [];
  const place = scene.placeNotes?.filter(Boolean).join(' ') ?? '';
  lines.push(`场景：${scene.location}${place ? `。${place}` : ''}`);
  if (scene.present?.length) {
    const people = scene.present.map((entry) => (entry.note ? `${entry.name}（${entry.note}）` : entry.name));
    lines.push(`在场人物：${people.join('；')}。`);
  }
  if (scene.objects?.length) {
    const objects = scene.objects.map((entry) => (entry.note ? `${entry.name}（${entry.note}）` : entry.name));
    lines.push(`在场物品：${objects.join('；')}。`);
  }
  return lines;
}

const TIME_WORDS: Record<string, string> = {
  second: '秒', minute: '分钟', hour: '小时', day: '天', turn: '回合',
};
function timeUnitWord(unit: string): string { return TIME_WORDS[unit] ?? unit; }

export function normalizeTime(
  value: CandidatePolicy['time'],
): { amount: number; unit: TimeAdvance['duration']['unit'] } | null {
  if (!value) return null;
  if ('duration' in value) return value.duration ?? null;
  return value;
}

function trim(text: string, max: number): string {
  const chars = [...text.trim()];
  return chars.length <= max ? chars.join('') : `${chars.slice(0, max).join('')}…`;
}

/** The exact message list for a chat checkpoint. */
export function buildMessages(spec: ModelSpec, userText: string): ChatTurn[] {
  if (!spec.template.systemMessage) return [{ role: 'user', content: userText }];
  return [
    { role: 'system', content: NARRATOR_SYSTEM_PROMPT },
    { role: 'user', content: userText },
  ];
}

/** Fallback for an engine without chat(): a plain, labelled prompt. This is
 * NOT a substitute template for a trained model; chat checkpoints should get
 * their real template through chat(). */
export function renderFallbackPrompt(spec: ModelSpec, userText: string): string {
  if (!spec.template.systemMessage) return userText;
  return `${NARRATOR_SYSTEM_PROMPT}\n\n${userText}`;
}

const THINK_OPEN = '<think>';
const THINK_CLOSE = '</think>';

/** Remove a leading/enclosed think block from a complete answer. */
export function stripThinking(text: string): string {
  let output = text;
  const open = output.indexOf(THINK_OPEN);
  const close = output.indexOf(THINK_CLOSE);
  if (open !== -1 && close > open) output = output.slice(0, open) + output.slice(close + THINK_CLOSE.length);
  else if (output.trimStart().startsWith(THINK_OPEN)) output = ''; // unclosed: nothing usable yet
  return output.replace(/^\s+/, '');
}

/** Incremental filter for streaming: emits only text outside think blocks.
 * A chunk boundary can split the tag, so a trailing partial tag is held back
 * until more text arrives. */
export class ThinkingFilter {
  private buffer = '';
  private inThink = false;
  private emitted = '';

  /** Returns the displayable text appended by this chunk. */
  push(chunk: string): string {
    this.buffer += chunk;
    let added = '';
    while (this.buffer.length > 0) {
      if (this.inThink) {
        const close = this.buffer.indexOf(THINK_CLOSE);
        if (close === -1) {
          // Keep only a suffix that could still become the closing tag.
          this.buffer = this.buffer.slice(Math.max(0, this.buffer.length - (THINK_CLOSE.length - 1)));
          return added;
        }
        this.buffer = this.buffer.slice(close + THINK_CLOSE.length);
        this.inThink = false;
        continue;
      }
      const open = this.buffer.indexOf(THINK_OPEN);
      if (open === -1) {
        // Emit everything except a possible partial opening tag at the end.
        const held = partialTagSuffix(this.buffer, THINK_OPEN);
        const emit = this.buffer.slice(0, this.buffer.length - held);
        if (emit) { this.emitted += emit; added += emit; }
        this.buffer = this.buffer.slice(this.buffer.length - held);
        return added;
      }
      if (open > 0) { const emit = this.buffer.slice(0, open); this.emitted += emit; added += emit; }
      this.buffer = this.buffer.slice(open + THINK_OPEN.length);
      this.inThink = true;
    }
    return added;
  }

  /** Flush any held partial tag when generation ends. */
  flush(): string {
    let added = '';
    if (!this.inThink) {
      const rest = this.buffer;
      this.buffer = '';
      // A dangling partial tag is model noise, not prose.
      const keep = rest.endsWith('<') || rest.endsWith('</') || rest.endsWith('<think') ? '' : rest;
      if (keep) { this.emitted += keep; added += keep; }
    }
    this.buffer = '';
    this.inThink = false;
    return added;
  }

  get text(): string { return this.emitted; }
}

function partialTagSuffix(text: string, tag: string): number {
  const limit = Math.min(tag.length - 1, text.length);
  for (let length = limit; length > 0; length -= 1) {
    if (text.endsWith(tag.slice(0, length))) return length;
  }
  return 0;
}

/** Clean a finished answer for display/storage: think block out, common
 * chat-model noise out (role prefixes, markdown fences, 「正文」 labels). */
export function cleanNarration(text: string): string {
  let output = stripThinking(text);
  output = output.replace(/^\s*```[a-z]*\s*/i, '').replace(/\s*```\s*$/, '');
  output = output.replace(/^\s*(?:正文|叙事|回答|输出)[:：]\s*/u, '');
  output = output.replace(/<\|im_end\|>/g, '').replace(/<\|endoftext\|>/g, '');
  return output.replace(/[ \t\u3000]+$/gm, '').trim();
}

export { NARRATOR_SYSTEM_PROMPT, describeCommitted };
