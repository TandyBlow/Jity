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
    // The model kept writing “罗青停在她面前” and “走过来”, which is true in the
    // fiction but does not state the committed from→to pair. Ask for one
    // explicit sentence per fact instead of a pronoun-only paraphrase.
    if (projected.packet.facts.some((fact) => fact.kind === 'moved')) {
      lines.push('每条移动事实都要用一句明确写出人名和两个地点，不要只用「他走过来」代替。');
    }
  } else {
    lines.push('这一小段时间里没有实体变化。视角人物停在原地：不要走向、靠近、离开或转向任何地点，也不要写任务达成或新的动作。');
  }
  const time = normalizeTime(policy.time);
  if (time) {
    lines.push(`本回合经过的时间：${time.amount}${timeUnitWord(time.unit)}。正文里要明确写出「${time.amount}${timeUnitWord(time.unit)}」。`);
  }
  const allPositions = mergePositions(policy.knownPositions, projected.positions);
  const presentNames = new Set((scene?.present ?? []).map((entry) => entry.name));
  const hasMove = projected.packet.facts.some((fact) => fact.kind === 'moved');
  // 09's driver offers every character's position, and a 1.5B model recited the
  // whole roster (“芬格尔在器材棚，楚子航在钟楼…”) instead of writing a scene.
  // For an opening (no movement) the scene block already names who is here, so
  // the position list is omitted; for a move only the people in this scene are
  // listed, to say who stayed.
  const positions = hasMove
    ? allPositions.filter((entry) => presentNames.size === 0 || presentNames.has(entry.name))
    : [];
  if (positions.length > 0) {
    lines.push('此刻的站位（已经如此，不必逐条复述）：');
    for (const entry of positions) lines.push(`- ${entry.name}在${entry.location}。`);
  }
  // Both models invented extra movement for the viewpoint character right
  // next to the required move. Naming who stayed is cheap; do NOT enumerate
  // forbidden verbs (the model then writes “她没有打开它”, which the shared
  // grader flags as an item event because it does not read negation).
  const moved = new Set(projected.packet.facts.filter((fact) => fact.kind === 'moved').map((fact) => fact.name));
  const still = hasMove
    ? [...new Set([
      ...(policy.roster ?? []),
      ...(scene?.present ?? []).map((entry) => entry.name),
      ...positions.map((entry) => entry.name),
    ])].filter((name) => !moved.has(name) && (presentNames.size === 0 || presentNames.has(name)))
    : [];
  if (still.length > 0) {
    lines.push(`本回合没有移动的人：${still.join('、')}。他们留在原地。`);
  }
  lines.push('除了上面列出的，这一小段时间里没有别的事件：人物位置和物品都保持原样。');
  // The raw serializer string is evidence for the caller, not material for the
  // prose: feeding 【状态】/【变化】 labels to an instruction model invites it to
  // copy the state format instead of writing a scene. Opt-in only.
  if (policy.includeInputText && inputText.trim()) {
    lines.push(`本点输入资料（只作依据，不要逐项复述，不要照抄字段名）：
${trim(inputText, 1200)}`);
  }
  if (policy.includePriorText && policy.priorText) {
    // Off by default: Qwen3-1.7B shown even the tail copied it (63% bigram
    // overlap) and re-stated stale positions. `priorText` is still used by the
    // repetition check; the prompt only gets it when a caller asks for it.
    lines.push(`上一段的结尾（只用来衔接语气，不要照抄）：
…${tail(policy.priorText, 90)}`);
  }
  const target = policy.targetChars;
  const paragraphs = policy.paragraphs ?? 3;
  const length = target
    ? `写成 ${paragraphs} 段，合计 ${Math.max(policy.minChars ?? Math.round(target * 0.75), 1)}～${target} 字。`
    : `写成 ${paragraphs} 段，合计约 180～260 字。`;
  const timeHint = time ? `；正文里必须出现「${time.amount}${timeUnitWord(time.unit)}」` : '';
  lines.push(`要求：${length}段与段之间空一行，直接给正文，不要小标题，不要解释${timeHint}。`);
  // Length is the failure the first real run actually showed: a 1.7B model
  // stops after two sentences because it thinks the scene is over.
  if (target) lines.push(`写满目标字数再把这一段场景收住，中途不要概括、不要跳跃。`);
  lines.push('用具体的动作、声音和细节推进，不要把「这一小段时间里发生的事」逐条翻译成句子。');
  // The same run invented an unlisted box opening. Banning unlisted
  // interaction is cheaper than one repair call and keeps the fact grader
  // meaningful.
  lines.push('没有变化的人物可以保持不动，只写视角人物看到、听到、想到的东西。');
  if (policy.instruction) lines.push(`补充要求：${policy.instruction}`);
  // 09 offers every character/location/item in the world as `knownEntities`
  // (120+ names for the free-day world). Listing them all invites name-dropping
  // and roster recitals, so keep only names this point can actually use: the
  // viewpoint, the scene's people/objects/place, and the fact actors.
  const usableNames = new Set<string>([
    ...(viewName ? [viewName] : []),
    ...(scene ? [scene.location] : []),
    ...(scene?.present ?? []).map((entry) => entry.name),
    ...(scene?.objects ?? []).map((entry) => entry.name),
    ...projected.packet.facts.map((fact) => fact.name),
    ...(policy.viewpoint?.name ? [policy.viewpoint.name] : []),
  ]);
  const knownEntities = (policy.knownEntities ?? []).filter((name) => !scene || usableNames.has(name));
  if (knownEntities.length > 0) {
    lines.push(`可用专名：${knownEntities.join('、')}。不得出现名单外的专名。`);
  }
  return lines.join('\n');
}

function renderScene(scene: CandidateScene | null): string[] {
  if (!scene) return [];
  const lines: string[] = [];
  const place = scene.placeNotes?.filter(Boolean).join(' ') ?? '';
  lines.push(`场景：${scene.location}${place ? `。${place}` : ''}`);
  // Long appearance notes are quoted verbatim by 1.5B/1.7B ("红发用发圈束在脑后，
  // 红色识别带缠在左臂…"). The first two clauses carry the visible detail; the
  // rest is state that belongs to the world, not to this passage.
  const clip = (note: string) => {
    const clauses = note.split(/[；;]/).map((part) => part.trim()).filter(Boolean).slice(0, 2).join('；');
    return [...clauses].length > 64 ? `${[...clauses].slice(0, 64).join('')}…` : clauses;
  };
  if (scene.present?.length) {
    const people = scene.present.map((entry) => (entry.note ? `${entry.name}（${clip(entry.note)}）` : entry.name));
    lines.push(`在场人物：${people.join('；')}。`);
  }
  if (scene.objects?.length) {
    const objects = scene.objects.map((entry) => (entry.note ? `${entry.name}（${clip(entry.note)}）` : entry.name));
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

function tail(text: string, max: number): string {
  const chars = [...text.trim()];
  return chars.length <= max ? chars.join('') : `…${chars.slice(-max).join('')}`;
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
