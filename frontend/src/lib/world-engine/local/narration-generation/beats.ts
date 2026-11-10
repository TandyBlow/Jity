/** Beat-scoped scene writing for small local models.
 *
 * The measured failure of one-shot scene generation is not bad Chinese: the
 * 0.5B/1.5B checkpoints write fluent paragraphs but keep adding events,
 * people and past that no committed fact contains, and they drop the one
 * change the point actually settled. Asking for a whole scene from a state
 * dump asks the model to invent connective tissue; that is exactly what it
 * does.
 *
 * This module turns the committed fact packet into an ordered list of small
 * writing beats. Each beat names one settled thing, the viewpoint, the place
 * and the people that beat may mention, and forbids everything else. The
 * model writes one to two sentences per beat. The beat text is verified on
 * its own, so a violated sentence is repaired or replaced without throwing
 * away the rest of the scene.
 *
 * Nothing here decides world facts: beats are derived from the caller's
 * `CommittedNarration` and the policy's licensed names. The plan is prose
 * instruction, not a second state authority.
 */
import type { TimeAdvance } from '../../types';
import type { CommittedNarration, NarrationFact } from '../../runtime/committed-narration';
import { factPhrases } from '../../runtime/committed-narration';
import type { BeatSceneContext, NarrationLedger, NarrationPolicy } from './types';
import { ownerOf } from './scene-prompt';

export type BeatKind = 'scene' | 'fact' | 'time';

export interface NarrationBeat {
  id: string;
  kind: BeatKind;
  /** Committed fact this beat must express; null for scene/time beats. */
  fact: NarrationFact | null;
  /** Imperative one-line statement of what to write. */
  directive: string;
  /** Phrases the beat text must contain for the fact to count as expressed. */
  anchors: string[];
  /** Names this beat may mention. */
  licensed: string[];
  /** Whether a failed beat may be replaced by the committed fact sentence. */
  fallback: 'fact-sentence' | 'time-sentence' | 'skip';
  /** Whether a missing beat is a scene-level hard failure. */
  mandatory: boolean;
}

const FACT_ORDER: Record<NarrationFact['kind'], number> = {
  at: 0, moved: 1, task_achieved: 2, personality_changed: 3, sanity: 4, sanity_changed: 4,
};

const CN_DIGITS = ['零', '一', '两', '三', '四', '五', '六', '七', '八', '九', '十'];
const UNIT_CN: Record<TimeAdvance['duration']['unit'], string> = {
  second: '秒', minute: '分钟', hour: '小时', day: '天', month: '个月', year: '年',
};
const cnAmount = (value: number): string =>
  (Number.isInteger(value) && value >= 0 && value <= 10 ? CN_DIGITS[value] : String(value));

/** The sentence used when the model cannot produce a faithful beat. It is a
 * plain narrative sentence about one committed fact, not a state listing. */
export function beatFallbackSentence(beat: NarrationBeat): string {
  const fact = beat.kind === 'fact' ? beat.fact : null;
  if (!fact) return '';
  switch (fact.kind) {
    case 'at': return `${fact.name}在${fact.location}。`;
    case 'moved': return `${fact.name}从${fact.from}走到了${fact.to}。`;
    case 'task_achieved': return `${fact.name}把「${fact.goal}」这件事做完了。`;
    case 'personality_changed': return `${fact.name}${fact.text}。`;
    case 'sanity': return `${fact.name}的精神值是${fact.value}。`;
    case 'sanity_changed': return `${fact.name}的精神值从${fact.from}变成了${fact.to}。`;
    default: return `${factPhrases(fact)[0]}。`;
  }
}

const TIME_PHRASES = [
  (amount: string, unit: string) => `约${amount}${unit}过去了。`,
  (amount: string, unit: string) => `${amount}${unit}就这么过去了。`,
  (amount: string, unit: string) => `等回过神来，${amount}${unit}已经过去。`,
  (amount: string, unit: string) => `又过了${amount}${unit}。`,
];

/** A time sentence that does not repeat what the previous scene already said.
 * The previous accepted prose is part of the point's context; re-using its
 * exact sentence is an echo, not continuity. */
export function timeFallbackSentence(
  duration: TimeAdvance['duration'],
  priorText?: string | null,
  offset = 0,
): string {
  const amount = cnAmount(duration.amount);
  const unit = UNIT_CN[duration.unit];
  const candidates = [...TIME_PHRASES.slice(offset), ...TIME_PHRASES.slice(0, offset)]
    .map((phrase) => phrase(amount, unit));
  return candidates.find((sentence) => !priorText || !priorText.includes(sentence)) ?? candidates[0];
}

function factDirective(fact: NarrationFact, scene: BeatSceneContext | undefined, viewpointName: string | null): string {
  const place = scene?.location ? `在${scene.location}` : '';
  switch (fact.kind) {
    case 'at':
      return `${fact.name}在${fact.location}。写${fact.name}${place ? '' : '此刻'}待在那里的样子，动作要小。`;
    case 'moved':
      return `${fact.name}从${fact.from}走到${fact.to}。写这段走动，以及${fact.name}到了之后停下的样子。`;
    case 'task_achieved':
      return `${fact.name}把「${fact.goal}」这件事做完了。写做完的那一刻，不要提前写后面的任务。`;
    case 'personality_changed':
      return `${fact.name}身上多了一点变化：${fact.text}。用动作或说话让人看出来，不要直接解释性格。`;
    case 'sanity':
      return `${fact.name}的精神状态是${fact.value}。用看得见的反应写出来，不要报数字。`;
    case 'sanity_changed':
      return `${fact.name}的精神状态从${fact.from}变到${fact.to}。用看得见的反应写出来，不要报数字。`;
    default:
      return viewpointName ? `${viewpointName}看着眼前的事。` : '写眼前发生的事。';
  }
}

export function planBeats(input: {
  committed: CommittedNarration;
  ledger: NarrationLedger;
  policy: NarrationPolicy;
  scene?: BeatSceneContext | null;
}): NarrationBeat[] {
  const { ledger, policy, scene } = input;
  const viewpointName = ledger.viewpoint?.name ?? null;
  const beats: NarrationBeat[] = [];

  const facts = [...ledger.mandatory].sort((a, b) => FACT_ORDER[a.kind] - FACT_ORDER[b.kind]);
  // A point with nothing settled still needs a readable scene; it gets a
  // longer opening beat and no fact beats to carry the scene.
  const quiet = facts.length === 0 && !(ledger.requireTime && ledger.time);

  if (scene && (scene.placeNotes?.length || scene.present?.length || scene.location)) {
    // The place notes already appear once, under 【环境】. Repeating them in
    // the directive made the model copy them as prose.
    const people = (scene.present ?? []).map((person) => person.name).filter((name) => name !== viewpointName);
    const parts = [scene.location ? `这里是${scene.location}` : null, people.length ? `${people.join('、')}也在` : null]
      .filter((part): part is string => Boolean(part));
    beats.push({
      id: 'scene-open',
      kind: 'scene',
      fact: null,
      directive: quiet
        ? `${parts.join('。')}。写三到四句眼前的场景：光、声音、手上的东西、${viewpointName ?? '主角'}的一个小动作。不要写任何人走动、开门、递东西、说话或回忆。`
        : `${parts.join('。')}。写一到两句眼前的场景：光、声音、手上的动作。不要写任何人走动、开门、递东西或说话。`,
      anchors: [],
      licensed: [
        ...people,
        ...(scene.location ? [scene.location] : []),
        ...(scene.objects ?? []).map((object) => object.name),
      ],
      fallback: 'skip',
      mandatory: quiet,
    });
  }

  for (const [index, fact] of facts.entries()) {
    beats.push({
      id: `fact-${index}-${fact.kind}`,
      kind: 'fact',
      fact,
      directive: factDirective(fact, scene ?? undefined, viewpointName),
      anchors: factPhrases(fact),
      licensed: [
        fact.name,
        ...(fact.kind === 'moved' ? [fact.from, fact.to] : []),
        ...(fact.kind === 'at' ? [fact.location] : []),
      ],
      fallback: 'fact-sentence',
      mandatory: true,
    });
  }

  if (ledger.requireTime && ledger.time) {
    const duration = ledger.time.duration;
    beats.push({
      id: 'time',
      kind: 'time',
      fact: null,
      directive: `时间过去了${cnAmount(duration.amount)}${UNIT_CN[duration.unit]}。用一句写这段时间是怎么过去的，不要写新的动作或事件。`,
      anchors: [`${duration.amount}${UNIT_CN[duration.unit]}`, `${cnAmount(duration.amount)}${UNIT_CN[duration.unit]}`],
      licensed: [],
      fallback: 'time-sentence',
      mandatory: true,
    });
  }

  void policy;
  return beats;
}

export interface BeatPromptInput {
  beat: NarrationBeat;
  ledger: NarrationLedger;
  policy: NarrationPolicy;
  scene?: BeatSceneContext | null;
  /** Sentences already written for this scene, oldest first. */
  written: readonly string[];
  /** First sentence of the previous accepted scene, for continuity. */
  priorTail?: string | null;
}

/** One beat prompt. Kept short on purpose: tiny models lose the instruction
 * after a long state dump, and this prompt must stay under ~200 tokens so the
 * first beat streams in about a second. */
const trimNote = (note: string): string => {
  const clean = note.replace(/[。.]+$/u, '').trim();
  return clean.length > 42 ? `${clean.slice(0, 42)}…` : clean;
};

export function buildBeatPrompt(input: BeatPromptInput): string {
  const { beat, ledger, policy, scene } = input;
  const lines: string[] = ['你是中文小说作者。只写下面这一件事，用一到两句，直接写正文。', ''];
  if (ledger.viewpoint) {
    lines.push(`【视角】${ledger.viewpoint.name}（第三人称；只写${ledger.viewpoint.name}看得见、听得见的东西，不写别人的内心）`);
  }
  if (scene?.location) lines.push(`【地点】${scene.location}`);
  // A present character's visible detail is settled state. Naming the person
  // without it invited the model to invent an appearance or a held object.
  const present = (scene?.present ?? []).filter((person) => person.name !== ledger.viewpoint?.name);
  if (present.length) {
    lines.push(`【在场】${present.map((person) => {
      const note = person.note?.trim();
      return note ? `${person.name}（${trimNote(note)}）` : person.name;
    }).join('；')}`);
  }
  const notes = (scene?.placeNotes ?? []).slice(0, 2);
  if (notes.length) lines.push(`【环境】${notes.join('；')}`);
  // Objects in the room are settled state too: naming one gives the model
  // something concrete to touch instead of inventing a prop.
  const objects = (scene?.objects ?? [])
    .slice(0, 3)
    .map((object) => {
      const owner = ownerOf(object.name);
      const note = object.note?.trim();
      return `${object.name}${owner ? `（属于${owner}${note ? `；${trimNote(note)}` : ''}）` : note ? `（${trimNote(note)}）` : ''}`;
    });
  if (objects.length) lines.push(`【手边】${objects.join('、')}`);
  const prior = input.written.length ? input.written.at(-1) ?? '' : (input.priorTail ?? '');
  if (prior) lines.push(`【前一句】${prior}`);
  lines.push(`【这一件】${beat.directive}`);
  // Dialogue, the viewpoint's own feelings and ordinary figurative language
  // are allowed polish (goal §137). Only another character's inner life and
  // new plot facts are forbidden; an earlier prompt banned all three and
  // produced flat, unnarratable sentences.
  lines.push('【要求】写具体的动作或手上的东西；对话用「」；不新增人物、物品、事件、往事、承诺和数字；'
    + '可以写视角人物的感受和判断，不要写别人心里怎么想；不要重复上面的说明；不要标题。');
  lines.push('称呼人物用名字，不要用他/她指代；只写【环境】里给出的声音和气味；属于某人的东西只写在那个人手上。');
  lines.push('不要写上面没有给出的姿势（蹲下、坐下、靠墙、站起）；人物保持原本的姿态。');
  lines.push('不要写「完成了一项任务」「个性发生了变化」「新增一条待办」这类报告句式，把结果写进动作或对话里。');
  const extra = policy.instruction?.trim();
  if (extra) lines.push(extra);
  lines.push('正文：');
  return lines.join('\n');
}
