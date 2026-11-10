/** Program realizer: settled fact -> readable prose.
 *
 * Every sentence here is built from a fact payload or from a description that
 * already exists in the settled state. The realizer adds only micro-actions
 * (a pause, a breath, a glance) and never a new person, prop, weather, past
 * event, clue or promise. Variants are drawn deterministically from the beat
 * seed, and repeated sentences/openings are avoided within a text and against
 * the previous accepted turn.
 */
import type { TimeAdvance } from '../../../types';
import { cnNumber } from '../../../runtime/narration-alignment';
import type { BeatDirective, SceneFact, SceneSkeleton } from './types';

const PARA_BREAK = String.fromCharCode(10, 10);

const UNIT_LABEL: Record<TimeAdvance['duration']['unit'], string> = {
  second: '秒', minute: '分钟', hour: '小时', day: '天', month: '个月', year: '年',
};

export function durationLabel(advance: TimeAdvance): string {
  const amount = advance.duration.amount;
  const read = amount === 2 ? '两' : amount === 1 ? '一' : cnNumber(amount) ?? String(amount);
  const unit = UNIT_LABEL[advance.duration.unit];
  if (advance.duration.unit === 'hour' || advance.duration.unit === 'month') {
    return `${read}个${advance.duration.unit === 'hour' ? '小时' : '月'}`;
  }
  return `${read}${unit}`;
}

export const SANITY_DOWN_CUES = ['沉', '紧', '往下', '发凉', '收紧', '坠', '缩'];
export const SANITY_UP_CUES = ['松', '顺', '稳', '回暖', '舒', '缓', '放平'];

export function sanityDirection(from: number, to: number): 'down' | 'up' | 'flat' {
  if (to < from) return 'down';
  if (to > from) return 'up';
  return 'flat';
}

function pick(seed: number, salt: string, size: number): number {
  if (size <= 1) return 0;
  let value = seed >>> 0;
  for (let index = 0; index < salt.length; index += 1) {
    value ^= salt.charCodeAt(index);
    value = Math.imul(value, 16777619) >>> 0;
  }
  return value % size;
}

function stripEnd(text: string): string {
  return text.replace(/[。！？!?；;，,、\s]+$/u, '').trim();
}

function asSentence(text: string): string {
  const clean = stripEnd(text);
  return clean ? `${clean}。` : '';
}

function bigrams(text: string): Set<string> {
  const stripped = text.replace(/[\s，。！？；：、「」“”"'（）()]/gu, '');
  const out = new Set<string>();
  for (let index = 0; index + 1 < stripped.length; index += 1) out.add(stripped.slice(index, index + 2));
  return out;
}

function overlaps(left: string, right: string): number {
  const a = bigrams(left);
  const b = bigrams(right);
  if (!a.size || !b.size) return 0;
  let shared = 0;
  for (const gram of a) if (b.has(gram)) shared += 1;
  return shared / Math.max(a.size, b.size);
}

/** Description clause safe to use as a scene detail. */
function clause(text: string, max = 30): string {
  const clean = text.replace(/\s+/gu, ' ').trim();
  if (!clean) return '';
  const parts = clean.split(/[。；;!?！？]/u).map((part) => part.trim()).filter(Boolean);
  let picked = parts[0] ?? clean;
  const commaParts = picked.split(/[，,]/u);
  if (picked.length > max && commaParts.length > 1) {
    picked = commaParts[0];
    for (let index = 1; index < commaParts.length; index += 1) {
      const next = `${picked}，${commaParts[index]}`;
      if (next.length > max) break;
      picked = next;
    }
  }
  return stripEnd(picked);
}

/** A complete settled sentence, shortened only at a comma and marked with an
 * ellipsis when it does not fit. Cutting a rule list at a semicolon would read
 * as if the rest of the rule did not exist. */
function sentenceClause(text: string, max = 64): string {
  const clean = text.replace(/\s+/gu, ' ').trim();
  if (!clean) return '';
  const end = clean.search(/[。！？!?]/u);
  const sentence = end >= 0 ? clean.slice(0, end) : clean;
  if ([...sentence].length <= max) return stripEnd(sentence);
  const cut = [...sentence].slice(0, max).join('');
  const comma = Math.max(cut.lastIndexOf('，'), cut.lastIndexOf('、'), cut.lastIndexOf('；'));
  const kept = (comma > max * 0.4 ? cut.slice(0, comma) : cut).replace(/[，、；]+$/u, '');
  return `${kept}……`;
}

export interface RealizerContext {
  scene: SceneSkeleton;
  priorText: string | null;
  /** Sentences already used in this text (dedupe). */
  used: Set<string>;
  /** Prefer the numeric sanity statement (legacy alignment gate). */
  sanityStyle: 'direction' | 'number';
  /** Openings used by previous accepted turns; avoid repeating them. */
  avoidOpenings: string[];
}

export function createRealizerContext(
  scene: SceneSkeleton,
  priorText: string | null,
  sanityStyle: 'direction' | 'number',
): RealizerContext {
  return { scene, priorText, used: new Set(), sanityStyle, avoidOpenings: [] };
}

export function realizeBeat(beat: BeatDirective, ctx: RealizerContext): string {
  const facts = beat.factIds
    .map((id) => ctx.scene.facts.find((fact) => fact.id === id))
    .filter((fact): fact is SceneFact => Boolean(fact));
  if (beat.kind === 'open') return openBeat(beat, ctx);
  if (beat.kind === 'move') return moveBeat(beat, facts, ctx);
  if (beat.kind === 'event') return eventBeat(beat, facts, ctx);
  if (beat.kind === 'result') return resultBeat(facts, ctx);
  if (beat.kind === 'scene') return sceneBeat(beat, facts, ctx);
  return closeBeat(beat, ctx);
}

function remember(ctx: RealizerContext, sentence: string): string {
  if (!sentence) return '';
  ctx.used.add(stripEnd(sentence));
  return sentence;
}

function acceptable(ctx: RealizerContext, sentence: string): boolean {
  if (ctx.used.has(stripEnd(sentence))) return false;
  if (ctx.avoidOpenings.some((opening) => opening && stripEnd(sentence).startsWith(stripEnd(opening)))) return false;
  if (ctx.priorText && overlaps(sentence, ctx.priorText) > 0.55) return false;
  return true;
}

function choose(ctx: RealizerContext, seed: number, salt: string, variants: string[]): string {
  const clean = variants.map((variant) => stripEnd(variant)).filter(Boolean);
  if (!clean.length) return '';
  const start = pick(seed, salt, clean.length);
  for (let offset = 0; offset < clean.length; offset += 1) {
    const candidate = clean[(start + offset) % clean.length];
    if (acceptable(ctx, candidate)) return `${candidate}。`;
  }
  return `${clean[start]}。`;
}

function openBeat(beat: BeatDirective, ctx: RealizerContext): string {
  const { scene } = ctx;
  const paragraphs: string[] = [];
  const time = scene.facts.find((fact) => beat.factIds.includes(fact.id) && fact.kind === 'time');
  if (time && time.kind === 'time') {
    const label = durationLabel(time.advance);
    paragraphs.push(remember(ctx, choose(ctx, beat.seed, 'time', [
      `${label}过去了`,
      `过了${label}`,
      `${label}之后`,
    ])));
  }
  const detail = sentenceClause(scene.place.note, 48);
  const place = scene.place.name || scene.viewpoint.location;
  const viewpoint = scene.viewpoint.name;
  const viewpointMoved = scene.facts.some((fact) => fact.kind === 'move' && fact.viewpoint);
  const variants: string[] = [];
  // The room is described after the arrival, in the move beat, when the
  // viewpoint moves this point; describing it first would spoil the move.
  if (detail && !viewpointMoved) {
    if (detail.includes(place)) variants.push(detail);
    else {
      variants.push(`${place}里，${detail}`);
      variants.push(`${place}。${detail}`);
    }
  }
  // Only assert a standing position when the point itself says the viewpoint
  // is here (a move beat follows otherwise and would be told backwards).
  if (scene.facts.some((fact) => fact.kind === 'at' && fact.entityId === scene.viewpoint.id)) {
    variants.push(`${viewpoint}还在${place}`);
    variants.push(`${viewpoint}站在${place}`);
  }
  const opening = remember(ctx, choose(ctx, beat.seed, 'place', variants.filter(Boolean)));
  if (opening) paragraphs.push(opening);
  return paragraphs.filter(Boolean).join('\n\n');
}

type MoveFact = Extract<SceneFact, { kind: 'move' }>;

// Only verbs the legacy grader recognises as movement; anything else reads as
// an unbacked arrival.
const ARRIVAL_VERBS = ['走进', '走到', '来到', '进入'];

function moveVerb(fact: MoveFact, seed: number, salt: string): string {
  if (fact.entityKind === 'item') return '移到';
  return ARRIVAL_VERBS[pick(seed, salt, ARRIVAL_VERBS.length)];
}

function moveSentence(fact: MoveFact, seed: number, salt: string, ctx: RealizerContext): string {
  const verb = moveVerb(fact, seed, salt);
  if (fact.entityKind === 'item') {
    // An item leaving somebody's hands reads better than "从路明非移到".
    if (ctx.scene.present.some((person) => person.id === fact.fromId) || fact.fromId === ctx.scene.viewpoint.id) {
      return choose(ctx, seed, `${salt}:item`, [
        `${fact.name}从${fact.from}身上${verb}${fact.to}`,
        `${fact.name}离开${fact.from}的手边，${verb}${fact.to}`,
      ]);
    }
    return choose(ctx, seed, `${salt}:item`, [
      `${fact.name}从${fact.from}${verb}${fact.to}`,
      `${fact.name}被从${fact.from}${verb}${fact.to}`,
    ]);
  }
  const variants = [
    `${fact.name}从${fact.from}${verb}${fact.to}`,
    `${fact.name}离开${fact.from}，${verb}${fact.to}`,
    `${fact.name}没有停，从${fact.from}${verb}${fact.to}`,
  ];
  return choose(ctx, seed, `${salt}:move`, variants);
}

function moveBeat(beat: BeatDirective, facts: SceneFact[], ctx: RealizerContext): string {
  const paragraphs: string[] = [];
  const moves = facts.filter((fact): fact is MoveFact => fact.kind === 'move');
  for (const [index, fact] of moves.entries()) {
    paragraphs.push(remember(ctx, moveSentence(fact, beat.seed, `${beat.id}:${index}`, ctx)));
  }
  if (moves.some((fact) => fact.viewpoint) && ctx.scene.place.note) {
    const detail = sentenceClause(ctx.scene.place.note, 48);
    const alreadySaid = [...ctx.used].some((used) => used.includes(stripEnd(detail)));
    // Keep the room's name on the detail so it cannot read as a stray sign.
    const placeName = ctx.scene.place.name || ctx.scene.viewpoint.location;
    const framed = detail
      ? asSentence(detail.includes(placeName) ? detail : `${placeName}里，${detail}`)
      : '';
    if (framed && !alreadySaid && acceptable(ctx, framed)) paragraphs.push(remember(ctx, framed));
  }
  return paragraphs.filter(Boolean).join('\n\n');
}

function eventBeat(beat: BeatDirective, facts: SceneFact[], ctx: RealizerContext): string {
  const paragraphs: string[] = [];
  const push = (text: string) => {
    const sentence = asSentence(text);
    if (!sentence || ctx.used.has(stripEnd(sentence))) return;
    paragraphs.push(remember(ctx, sentence));
  };
  // Appearance first: the visible result before the inner consequence.
  for (const fact of facts) {
    if (fact.kind === 'appearance_changed') {
      const name = fact.name;
      if (fact.removed) {
        const old = fact.supersededTexts[0] ? clause(fact.supersededTexts[0], 18) : '';
        push(old
          ? choose(ctx, beat.seed, `${fact.id}:rm`, [`${name}不再像先前那样${old}`, `${name}身上，${old}的样子没有了`])
          : choose(ctx, beat.seed, `${fact.id}:rm2`, [`${name}身上先前那点变化淡了`]));
      } else if (fact.text) {
        const text = stripEnd(fact.text);
        if (fact.entityKind === 'location') {
          push(choose(ctx, beat.seed, `${fact.id}:loc`, [text]));
        } else {
          push(choose(ctx, beat.seed, `${fact.id}`, [
            `${name}身上，${text}`,
            `${name}看上去和先前不同：${text}`,
          ]));
        }
      }
    }
  }
  for (const fact of facts) {
    if (fact.kind === 'task_achieved') {
      push(choose(ctx, beat.seed, `${fact.id}`, [
        `${fact.name}完成了「${fact.goal}」`,
        `${fact.name}把「${fact.goal}」这件事做完了`,
      ]));
    }
    if (fact.kind === 'subtask_added') {
      push(choose(ctx, beat.seed, `${fact.id}`, [
        `${fact.name}给自己记下一条：${fact.goal}`,
        `${fact.name}还有下一件事要做：${fact.goal}`,
      ]));
    }
  }
  for (const fact of facts) {
    if (fact.kind === 'personality_changed') {
      if (fact.removed) {
        const old = fact.supersededTexts[0] ? clause(fact.supersededTexts[0], 16) : '';
        push(old
          ? choose(ctx, beat.seed, `${fact.id}:rm`, [`${fact.name}收起了「${old}」这一面`, `${fact.name}不再像先前那样${old}`])
          : choose(ctx, beat.seed, `${fact.id}:rm2`, [`${fact.name}的性子又变了一点`]));
      } else if (fact.text) {
        // Name first and no comma before the frozen text: the legacy grader
        // binds a personality change within the name clause plus two clauses,
        // so the full text has to start in the name clause.
        push(choose(ctx, beat.seed, `${fact.id}`, [
          `${fact.name}的性子变了一点：${fact.text}`,
          `${fact.name}身上多了一点变化：${fact.text}`,
        ]));
      }
    }
  }
  for (const fact of facts) {
    if (fact.kind === 'sanity_changed') {
      if (ctx.sanityStyle === 'number') {
        const from = cnNumber(fact.from) ?? String(fact.from);
        const to = cnNumber(fact.to) ?? String(fact.to);
        const verb = fact.to < fact.from ? '落到' : '回到';
        push(choose(ctx, beat.seed, `${fact.id}:n`, [
          `${fact.name}的精神值从${from}${verb}${to}`,
          `${fact.name}的数值从${from}${verb}${to}`,
        ]));
      } else {
        const direction = sanityDirection(fact.from, fact.to);
        push(choose(ctx, beat.seed, `${fact.id}:d`, direction === 'down' ? [
          `${fact.name}的呼吸沉了一格`,
          `${fact.name}喉咙紧了一下`,
          `${fact.name}的肩膀往下收了收`,
        ] : direction === 'up' ? [
          `${fact.name}的呼吸顺了回来`,
          `${fact.name}胸口松了一点`,
          `${fact.name}的肩膀松下来`,
        ] : [`${fact.name}的神色没有变`]));
      }
    }
  }
  return paragraphs.filter(Boolean).join('\n\n');
}

function resultBeat(facts: SceneFact[], ctx: RealizerContext): string {
  const result = facts.find((fact) => fact.kind === 'result');
  if (!result || result.kind !== 'result') return '';
  const text = result.text.trim();
  if (!text || ctx.used.has(stripEnd(text))) return '';
  return remember(ctx, text.endsWith('。') || text.endsWith('！') || text.endsWith('？') ? text : asSentence(text));
}

function sceneBeat(beat: BeatDirective, facts: SceneFact[], ctx: RealizerContext): string {
  const { scene } = ctx;
  const place = scene.place.name || scene.viewpoint.location;
  const paragraphs: string[] = [];
  const alreadySaid = (name: string): boolean => [...ctx.used].some((used) => used.includes(name));
  // A present character gives the room a witness instead of a list of props.
  const person = scene.present.find((entry) => !beat.mustMention.includes(entry.name)
    && entry.note && !alreadySaid(entry.name));
  if (person) {
    const detail = clause(person.note, 22);
    if (detail) {
      paragraphs.push(remember(ctx, choose(ctx, beat.seed, `${person.id}:at`, [
        `${person.name}也在${place}，${detail}`,
        `${place}里还有${person.name}，${detail}`,
      ])));
    }
  }
  for (const fact of facts) {
    if (fact.kind === 'item_present') {
      const detail = sentenceClause(fact.note, 56);
      paragraphs.push(remember(ctx, choose(ctx, beat.seed, `${fact.id}`, detail ? [
        `${fact.name}还在${fact.container}。${detail}`,
        `${fact.name}留在原处，${detail}`,
      ] : [
        `${fact.name}还在${fact.container}`,
        `${fact.name}留在${fact.container}`,
      ])));
    } else if (fact.kind === 'item_discovered') {
      const detail = sentenceClause(fact.note, 56);
      paragraphs.push(remember(ctx, choose(ctx, beat.seed, `${fact.id}`, detail ? [
        `${fact.name}就在${fact.container}。${detail}`,
        `${fact.container}里，${fact.name}还在原处；${detail}`,
      ] : [
        `${fact.name}就在${fact.container}`,
        `${fact.name}在${fact.container}，先前没有留意`,
      ])));
    }
  }
  // No item change this point: one existing object carries the room instead.
  if (!facts.length && person === undefined) {
    const object = scene.objects.find((entry) => entry.note && !alreadySaid(entry.name));
    if (object) {
      const detail = clause(object.note, 24);
      if (detail) {
        paragraphs.push(remember(ctx, choose(ctx, beat.seed, `${object.id}:note`, [
          `${object.name}在${place}，${detail}`,
          `${place}里，${object.name}还在原处；${detail}`,
        ])));
      }
    }
  }
  return paragraphs.filter(Boolean).join(PARA_BREAK);
}

function closeBeat(beat: BeatDirective, ctx: RealizerContext): string {
  const { scene } = ctx;
  const name = scene.viewpoint.name;
  const person = scene.present[0]?.name;
  const place = scene.place.name || scene.viewpoint.location;
  const variants = [
    `${name}没有马上再动`,
    `${name}把视线收回来`,
    `${name}在原地站了一会儿`,
    `${name}没有再往前`,
    `${name}站着没动`,
  ];
  if (person) {
    variants.push(`${person}也没有动`);
    variants.push(`${person}还站在那里`);
  }
  if (scene.timeOnly) {
    variants.push(`${name}留在${place}`);
  }
  return remember(ctx, choose(ctx, beat.seed, 'close', variants));
}
