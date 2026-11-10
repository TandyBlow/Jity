/** Independent narration review: facts, inventions, viewpoint, style.
 *
 * The review is sentence-scoped and keeps an explicit record for every
 * sentence: the text, the settled basis it uses, the finding kinds, and a
 * judgement. Sentences a machine cannot decide are `review`, never a pass.
 * Dialogue is always a review item because its content is a human judgement;
 * a dialogue line that asserts a past event, a promise or a number is still
 * checked against the settled input.
 */
import type { DatasetInput, SceneProjection } from './scene';
import { projectScene, parseMinutes } from './scene';
import {
  BODY_ACTIONS, BODY_REACTION, CHANGE_MARKERS, CLOSURE, COMPLETION_VERBS, EVENT_VERBS, FAREWELL,
  FIELD_WORDS, HOLD_MARKERS, INTERIOR, ITEM_STATE_VERBS, MOVE_VERBS, NEGATION,
  HANDLING_VERBS, INVENTABLE_OBJECTS, ITEM_HANDLING_VERBS, SPEECH_VERBS_UNQUOTED, PAST_MARKERS, POSSESSION_VERBS, POSTURE, PROMISE_VERBS, SANITY_DOWN, SANITY_UP, SOFT_EVENT_VERBS,
  SOUND_WORDS, TERMINAL_PUNCTUATION,
} from './lexicon';
import type { Finding, FindingKind, MandatoryReview, ReviewOptions, ReviewReport, SentenceReview } from './types';

/** Style findings that make a text unusable for a player even when the facts
 * are right. Register/field wording is reported separately. */
const SQUARE_FORM = new Set<string>(['style.status_panel', 'style.field_sentence']);
const BLOCKING_STYLE = new Set<string>([
  'style.status_panel', 'style.loop', 'style.echo_prior', 'style.repeated_opening',
  'style.truncated', 'style.premature_closure', 'style.meta', 'style.roster_recital',
]);

const PROPS = [
  '短枪', '演习枪', '长枪', '枪', '护目镜', '盒子', '盒盖', '规则牌', '路线图',
  '相机', '钥匙', '笔', '本子', '绳子', '旗', '旗杆', '弹匣', '担架', '保温毯',
  '水杯', '纸杯', '登记簿', '名单', '信号旗', '短讯机', '电池', '绷带', '手套',
  '背包', '纸', '纸条', '信封', '锁', '挂锁', '梯子', '门闩', '安全带',
];

const escapeRegExp = (value: string): string => value.replace(/[.*+?^${}()|[\]\\]/gu, '\\$&');

export interface SentenceParts {
  text: string;
  paragraph: number;
  /** Sentence with quoted spans emptied, for narration-side rules. */
  narration: string;
  quotes: string[];
}

/** Split on 。！？ and newlines, protecting quoted dialogue from splitting. */
export function splitSentences(text: string): SentenceParts[] {
  const parts: string[] = [];
  let buffer = '';
  let inQuote = false;
  const paragraphs: string[] = [];
  for (const char of text) {
    if (char === '「') inQuote = true;
    if (char === '」') inQuote = false;
    if (char === '\n') {
      if (buffer.trim()) paragraphs.push(buffer.trim());
      buffer = '';
      continue;
    }
    buffer += char;
    if (!inQuote && '。！？!?'.includes(char)) {
      paragraphs.push(buffer.trim());
      buffer = '';
    }
  }
  if (buffer.trim()) paragraphs.push(buffer.trim());
  for (const entry of paragraphs) {
    // A stray "。" left by duplicated punctuation is not a sentence.
    if (/[\p{Script=Han}A-Za-z0-9]/u.test(entry)) parts.push(entry);
  }
  return parts.map((entry, index) => {
    const quotes = [...entry.matchAll(/「([^」]*)」/gu)].map((match) => match[1]);
    return {
      text: entry,
      paragraph: paragraphFor(text, entry, index),
      narration: entry.replace(/「[^」]*」/gu, '「」'),
      quotes,
    };
  });
}

/** Paragraph index by counting newlines before the sentence. */
function paragraphFor(full: string, sentence: string, fallback: number): number {
  const index = full.indexOf(sentence);
  if (index < 0) return fallback;
  return full.slice(0, index).split('\n').length - 1;
}

function normalize(text: string): string {
  return text.replace(/[\s，。！？；：、「」『』“”"'…—\-·]/gu, '');
}

function hasAny(text: string, words: readonly string[]): string | null {
  for (const word of words) if (text.includes(word)) return word;
  return null;
}

function negatedAt(text: string, word: string): boolean {
  const pattern = new RegExp(`(?:${NEGATION})[^，。；]{0,3}${escapeRegExp(word)}`, 'u');
  return pattern.test(text);
}

function lastIndexCjk(before: string): boolean {
  if (!before) return false;
  return /[\u4e00-\u9fa5]/u.test(before.slice(-1));
}

/** All occurrences of `name` that are not part of a longer licensed name. */
function mentionIndexes(text: string, name: string, names: readonly string[]): number[] {
  const indexes: number[] = [];
  let start = 0;
  for (;;) {
    const index = text.indexOf(name, start);
    if (index < 0) break;
    start = index + 1;
    const longer = names.some((other) => other !== name && other.length > name.length
      && text.startsWith(other, index));
    // A one-character name inside a longer word is not a mention.
    if (longer) continue;
    if (name.length === 1 && lastIndexCjk(text.slice(0, index))) continue;
    indexes.push(index);
  }
  return indexes;
}

function mentions(text: string, name: string, names: readonly string[]): boolean {
  return mentionIndexes(text, name, names).length > 0;
}

interface NameHit {
  name: string;
  index: number;
}

function nameHits(text: string, names: readonly string[], only?: readonly string[]): NameHit[] {
  const allowed = only ?? names;
  const hits: NameHit[] = [];
  for (const name of allowed) {
    for (const index of mentionIndexes(text, name, names)) hits.push({ name, index });
  }
  return hits.sort((a, b) => a.index - b.index || b.name.length - a.name.length);
}

const PRONOUNS = ['他们', '她们', '他', '她'] as const;

interface PronounBinding {
  pronoun: string;
  gender: 'male' | 'female';
  antecedent: string | null;
  candidates: string[];
  /** `strong` means the reference is unambiguous from the text alone. */
  strength: 'strong' | 'ambiguous';
  index: number;
  sentence: number;
}

/** Pronoun resolution, deliberately conservative.
 *
 * Strong (unambiguous) cases only:
 *  - the pronoun starts a clause and the tracked subject is known;
 *  - the pronoun directly follows a name («周宁她»).
 * Anything else is ambiguous and becomes a review item: Chinese narration
 * omits subjects, and «林川站在他身后» does not name who 他 is.
 */
function pronounBindings(sentences: SentenceParts[], names: readonly string[], people: readonly string[] = names, genders?: Record<string, 'male' | 'female'>): PronounBinding[] {
  const bindings: PronounBinding[] = [];
  let subject: string | null = null;
  sentences.forEach((sentence, sentenceIndex) => {
    const narration = sentence.narration;
    const hits = nameHits(narration, names, people);
    if (hits[0]?.name) subject = hits[0].name;
    for (const pronoun of PRONOUNS) {
      const gender = pronoun.startsWith('她') ? 'female' : 'male';
      let start = 0;
      for (;;) {
        const index = narration.indexOf(pronoun, start);
        if (index < 0) break;
        start = index + 1;
        const clauseStart = Math.max(
          narration.lastIndexOf('，', index),
          narration.lastIndexOf('；', index),
          narration.lastIndexOf('。', index),
          narration.lastIndexOf('：', index),
        ) + 1;
        const clause = narration.slice(clauseStart, index);
        const local = nameHits(clause, names);
        // The clause immediately before this one, to find the real antecedent.
        const beforeStart = narration.lastIndexOf('，', clauseStart - 2) + 1;
        const previousClause = clauseStart > 0 ? narration.slice(Math.max(0, beforeStart), clauseStart - 1) : '';
        const previousNames = nameHits(previousClause, names);
        const direct = local.length === 1 && clause.trimEnd().endsWith(local[0].name)
          && clause.trimEnd().length - clause.indexOf(local[0].name) <= 2;
        if (index === clauseStart && previousNames.length === 1) {
          // "周宁把袖子卷起，他……" — the only person in the previous clause is
          // the antecedent, so the registry can judge the pronoun directly.
          bindings.push({ pronoun, gender, antecedent: previousNames[0].name, candidates: [previousNames[0].name], strength: 'strong', index, sentence: sentenceIndex });
          continue;
        }
        if (index === clauseStart && subject) {
          // A clause-initial pronoun continues the tracked subject — unless
          // the registry says that subject cannot be the referent and another
          // person in the scene can. Then it is genuinely ambiguous.
          const subjectGender = genders?.[subject];
          const alternative = people.find((name) => name !== subject
            && (genders?.[name] === gender || genders?.[name] === undefined));
          if (subjectGender && subjectGender !== gender && alternative) {
            bindings.push({ pronoun, gender, antecedent: null, candidates: [subject, alternative], strength: 'ambiguous', index, sentence: sentenceIndex });
            continue;
          }
          bindings.push({ pronoun, gender, antecedent: subject, candidates: [subject], strength: 'strong', index, sentence: sentenceIndex });
          continue;
        }
        if (direct) {
          bindings.push({ pronoun, gender, antecedent: local[0].name, candidates: [local[0].name], strength: 'strong', index, sentence: sentenceIndex });
          continue;
        }
        const candidates = [...new Set([...local.map((hit) => hit.name), ...(subject ? [subject] : []), ...(people.length === 1 ? people : [])])];
        // A scene with exactly one person has exactly one possible referent.
        if (!subject && people.length === 1) {
          bindings.push({ pronoun, gender, antecedent: people[0], candidates, strength: 'strong', index, sentence: sentenceIndex });
          continue;
        }
        bindings.push({
          pronoun, gender, antecedent: null, candidates, strength: 'ambiguous', index, sentence: sentenceIndex,
        });
      }
    }
  });
  return bindings;
}


/** The clause (，；：。 bounded) around `index`. */
function clauseAt(text: string, index: number): { start: number; end: number; text: string } {
  const boundaries = ['，', '；', '：', '。', '！', '？'];
  let start = 0;
  for (const mark of boundaries) {
    const position = text.lastIndexOf(mark, index - 1);
    if (position + 1 > start) start = position + 1;
  }
  let end = text.length;
  for (const mark of boundaries) {
    const position = text.indexOf(mark, index);
    if (position >= 0 && position < end) end = position;
  }
  return { start, end, text: text.slice(start, end) };
}

function possessionClause(text: string, object: string): string | null {
  const index = text.indexOf(object);
  if (index < 0) return null;
  const clause = clauseAt(text, index).text;
  const possessed = hasAny(clause, POSSESSION_VERBS) !== null
    || HOLD_MARKERS.some((marker) => clause.includes(marker))
    || /在(?:手里|手中|掌心|手心|身上)/u.test(clause);
  return possessed ? clause : null;
}

interface HolderMap {
  /** object word -> person name, or 'scene' when it lies in a place. */
  holders: Map<string, string>;
  basis: Map<string, string>;
}

function buildHolders(projection: SceneProjection): HolderMap {
  const holders = new Map<string, string>();
  const basis = new Map<string, string>();
  for (const [name, item] of Object.entries(projection.items)) {
    const position = item.positionAfter ?? item.positionBefore;
    if (!position) continue;
    const holder = projection.people[position] ? position : 'scene';
    holders.set(name, holder);
    basis.set(name, holder === 'scene' ? `${name} 在 ${position}` : `${holder} 携带 ${name}`);
    // A long item name is usually a head noun plus modifiers
    // (诺诺的演习短枪 -> 短枪 / 枪); the head is what prose names.
    for (const prop of PROPS) {
      if (prop.length >= 1 && name.includes(prop) && !holders.has(prop)) {
        holders.set(prop, holder);
        basis.set(prop, basis.get(name) as string);
      }
    }
  }
  for (const person of Object.values(projection.people)) {
    for (const description of person.appearanceAfter) {
      for (const marker of HOLD_MARKERS) {
        let start = 0;
        for (;;) {
          const index = description.indexOf(marker, start);
          if (index < 0) break;
          start = index + marker.length;
          const tail = description.slice(start);
          const prop = PROPS.find((entry) => tail.startsWith(entry)) ?? null;
          if (prop && !holders.has(prop)) {
            holders.set(prop, person.name);
            basis.set(prop, `${person.name} 的外貌：${description}`);
          }
        }
      }
      for (const verb of POSSESSION_VERBS) {
        const index = description.indexOf(verb);
        if (index < 0) continue;
        const tail = description.slice(index + verb.length);
        const prop = PROPS.find((entry) => tail.startsWith(entry)) ?? null;
        if (prop && !holders.has(prop)) {
          holders.set(prop, person.name);
          basis.set(prop, `${person.name} 的外貌：${description}`);
        }
      }
    }
  }
  return { holders, basis };
}

interface ReviewContext {
  projection: SceneProjection;
  options: ReviewOptions;
  holders: HolderMap;
  /** True when a word appears in a settled, non-conditional description. A
   * habitual trait ("听见远处枪声会下意识缩肩") does not license a current
   * gunshot or a current shrug. */
  stateLicensed: (word: string) => boolean;
  /** Sentence index currently being reviewed. */
  index: number;
}

/** Any string inside the point, for licence and trait checks. */
function collectStrings(value: unknown, out: string[] = []): string[] {
  if (typeof value === 'string') out.push(value);
  else if (Array.isArray(value)) for (const entry of value) collectStrings(entry, out);
  else if (value && typeof value === 'object') for (const entry of Object.values(value)) collectStrings(entry, out);
  return out;
}

/** Conditional or habitual wording: a rule the character follows, not an event. */
const CONDITIONAL = /(会|若|如果|一旦|一.{0,4}就|习惯|常常|总是|每次|每当|听见|听到)/u;
const OBJECT_SPEAKER_NAMES: string[] = [];

function finding(ctx: ReviewContext, kind: FindingKind, sentence: string, detail: string, basis: string[], factIds?: string[]): Finding {
  const severity = kind.startsWith('review.') ? 'review' : kind.startsWith('style.') ? 'style' : 'fact';
  return { kind, severity, sentence, detail, basis: basis.filter(Boolean), ...(factIds?.length ? { factIds } : {}) };
}

/** Is a verb licensed by the settled input or by a committed event? */
function verbLicensed(verb: string, ctx: ReviewContext, sentence: string): boolean {
  if (ctx.stateLicensed(verb)) return true;
  if (negatedAt(sentence, verb)) return true;
  // A completed task is settled evidence that the action it names happened
  // (e.g. 「更换空弹匣」 for a reload).
  if (ctx.projection.taskCompleted.some((task) => sentence.includes(task.goal))) return true;
  // A committed move licenses its own motion vocabulary only.
  if (MOVE_VERBS.includes(verb as typeof MOVE_VERBS[number])
    && ctx.projection.moves.some((move) => sentence.includes(move.name))) return true;
  return false;
}

function timeForms(text: string): number[] {
  const forms: number[] = [];
  const arabic = /(\d+)\s*(?:分钟|分)(?!钟)/gu;
  for (const match of text.matchAll(arabic)) forms.push(Number(match[1]));
  const chinese = /([零一二三四五六七八九十两半百]+)\s*(?:分钟|分)(?!钟)/gu;
  for (const match of text.matchAll(chinese)) {
    const minutes = parseMinutes(`${match[1]}分钟`);
    if (minutes !== null) forms.push(minutes);
  }
  return forms;
}

export function reviewNarration(args: {
  id: string;
  input: DatasetInput;
  text: string;
  options?: ReviewOptions;
}): ReviewReport {
  const { id, input, text } = args;
  const options = args.options ?? {};
  const projection = projectScene(input);
  const names = projection.names;
  const sentences = splitSentences(text);
  const findings: Finding[] = [];
  const settledStrings = collectStrings(input);
  OBJECT_SPEAKER_NAMES.length = 0;
  OBJECT_SPEAKER_NAMES.push(...Object.keys(projection.people));
  const stateLicensed = (word: string): boolean => settledStrings.some((entry) => entry.includes(word) && !CONDITIONAL.test(entry));
  const ctx: ReviewContext = { projection, options, holders: buildHolders(projection), stateLicensed, index: 0 };
  const sentenceReviews: SentenceReview[] = [];

  const charCount = [...text].length;
  const timeMinutes = projection.minutes;
  const forms = timeForms(text);
  const timeExpressed = timeMinutes !== null && forms.includes(timeMinutes);

  // ---------------------------------------------------------------- time
  if (timeMinutes === null) {
    const passage = /(?:(?:一|两|二|三|四|五|六|七|八|九|十|几|半)[^，。；]{0,3}(?:分钟|小时|秒)(?:过去|之后|后|里|以后)|(?:过了|又过了|过去)[^，。；]{0,6}(?:分钟|小时|秒))/u.exec(text);
    if (passage) {
      findings.push(finding(ctx, 'fact.time_added', sentences[0]?.text ?? text,
        `time passes in the prose (${passage[0]}) but the point settles no time advance`, []));
    }
  }
  if (timeMinutes !== null) {
    if (!timeExpressed) {
      findings.push(finding(ctx, 'fact.time_missing', sentences[0]?.text ?? text,
        `settled advance ${projection.timeText} is not stated`, [projection.timeText ?? '']));
    } else if (forms.filter((value) => value === timeMinutes).length > 1) {
      findings.push(finding(ctx, 'style.punctuation', sentences[0]?.text ?? text,
        `the same advance is stated ${forms.filter((value) => value === timeMinutes).length} times`,
        [projection.timeText ?? '']));
    }
  }

  // ---------------------------------------------------------------- moves
  const expressedMoves = new Set<string>();
  const moveSentences = new Map<string, string>();
  for (const sentence of sentences) {
    for (const move of projection.moves.filter((entry) => entry.kind === 'person')) {
      const subject = mentions(sentence.narration, move.name, names);
      if (!subject) continue;
      const toIndex = sentence.narration.indexOf(move.to);
      if (toIndex < 0) continue;
      const towards = new RegExp(`(?:往|朝|向)${escapeRegExp(move.to)}(?:那边|这边|方向)?(?:走|去|跑|挪)`, 'u').test(sentence.narration);
      const moveVerb = hasAny(sentence.narration, MOVE_VERBS);
      if (!moveVerb && !towards && !sentence.narration.includes('在')) continue;
      if (move.from) {
        const fromIndex = sentence.narration.indexOf(move.from);
        if (fromIndex >= 0 && fromIndex > toIndex) {
          findings.push(finding(ctx, 'fact.direction_reversed', sentence.text,
            `${move.name}: destination ${move.to} is stated before origin ${move.from}`,
            [`${move.name}: ${move.from} → ${move.to}`], [move.id]));
          continue;
        }
      }
      // "从X走来/进入…" states an origin. If X is a known place but not the
      // settled origin, the sentence invents a different route.
      const origin = /从([^，。；、「」]{1,10}?)(?:走来|走来过|走|来|跑|退|出|进|返回|回到|撤离|挪|移)/u.exec(sentence.narration);
      if (origin && move.from && !move.from.includes(origin[1])) {
        const named = origin[1].replace(/(?:里|中|内|上|外|边|口|侧)$/u, '');
        const knownPlace = Object.keys(projection.places).some((place) => place === origin[1] || place === named);
        if (knownPlace) {
          findings.push(finding(ctx, 'fact.wrong_source', sentence.text,
            `${move.name}: the sentence starts from ${origin[1]}, but the settled move starts from ${move.from}`,
            [`${move.name}: ${move.from} → ${move.to}`], [move.id]));
          continue;
        }
      }
      expressedMoves.add(move.id);
      moveSentences.set(move.id, sentence.text);
    }
  }
  const reversedMoves = new Set(findings
    .filter((entry) => entry.kind === 'fact.direction_reversed')
    .flatMap((entry) => entry.factIds ?? []));
  for (const move of projection.moves.filter((entry) => entry.kind === 'person')) {
    if (expressedMoves.has(move.id) || reversedMoves.has(move.id)) continue;
    const actorSeen = text.includes(move.name);
    const destinationSeen = text.includes(move.to);
    if (actorSeen && destinationSeen) {
      findings.push(finding(ctx, 'review.tone', moveSentences.get(move.id) ?? (sentences[0]?.text ?? text),
        `${move.name} and ${move.to} both appear but the move is not recognised; binding needs reading`,
        [`${move.name}: ${move.from ?? '?'} → ${move.to}`], [move.id]));
      continue;
    }
    findings.push(finding(ctx, 'fact.move_omitted', moveSentences.get(move.id) ?? (sentences[0]?.text ?? text),
      `${move.name}: ${move.from ?? '?'} → ${move.to} is not narrated`,
      [`${move.name}: ${move.from ?? '?'} → ${move.to}`], [move.id]));
  }

  // ------------------------------------------------------------ positions
  /** A slot id (`西侧服务巷/slot_wall`) is a spot inside the place; naming the
   * place itself is consistent. */
  const basePlace = (value: string | null): string | null => (value ? value.split('/')[0].trim() : null);
  for (const sentence of sentences) {
    for (const person of Object.values(projection.people)) {
      const settled = basePlace(person.positionAfter ?? person.positionBefore);
      if (!settled) continue;
      if (!mentions(sentence.narration, person.name, names)) continue;
      for (const place of Object.keys(projection.places)) {
        if (place === settled) continue;
        const pattern = new RegExp(`${escapeRegExp(person.name)}[^，。；]{0,6}(?:在|站在|坐在|蹲在|躺在|靠在|待在|留在|还在|守在|到了)${escapeRegExp(place)}(?![\\u4e00-\\u9fa5])`, 'u');
        // "在天台楼梯间" must not be read as "在天台".
        if (!pattern.test(sentence.narration)) continue;
        const isParent = isAncestor(place, settled, projection);
        if (isParent) continue;
        const movedHere = projection.moves.some((move) => move.kind === 'person' && move.name === person.name && move.to === place);
        if (movedHere) continue;
        findings.push(finding(ctx, 'fact.false_position', sentence.text,
          `${person.name} is settled at ${settled} but placed at ${place}`,
          [`${person.name} 位置：${settled}`], [`position:${person.name}`]));
        break;
      }
    }
  }

  // --------------------------------------------------------------- sanity
  const sanityLiteral = new Set<string>();
  const sanityReaction = new Set<string>();
  for (const change of projection.sanityChanges) {
    for (const sentence of sentences) {
      if (!mentions(sentence.narration, change.name, names)) continue;
      const numbers = [...sentence.narration.matchAll(/\d+/gu)].map((match) => Number(match[0]));
      const hasBoth = numbers.includes(change.from) && numbers.includes(change.to);
      const hasContext = /精神|理智|清醒/u.test(sentence.narration);
      if (hasBoth && hasContext) {
        sanityLiteral.add(change.id);
        continue;
      }
      const wrong = numbers.find((value) => ![change.from, change.to].includes(value));
      if (wrong !== undefined && hasContext) {
        findings.push(finding(ctx, 'fact.wrong_number', sentence.text,
          `${change.name}: ${wrong} is neither the settled ${change.from} nor ${change.to}`,
          [`${change.name} 精神值：${change.from} → ${change.to}`], [change.id]));
        continue;
      }
      if (!hasContext) continue;
      const up = hasAny(sentence.narration, SANITY_UP);
      const down = hasAny(sentence.narration, SANITY_DOWN);
      const rose = change.to > change.from;
      if (up && !down && !rose) {
        findings.push(finding(ctx, 'fact.wrong_number', sentence.text,
          `${change.name}: the stated direction rises but the settled change falls`,
          [`${change.name} 精神值：${change.from} → ${change.to}`], [change.id]));
        continue;
      }
      if (down && !up && rose) {
        findings.push(finding(ctx, 'fact.wrong_number', sentence.text,
          `${change.name}: the stated direction falls but the settled change rises`,
          [`${change.name} 精神值：${change.from} → ${change.to}`], [change.id]));
        continue;
      }
    }
    if (sanityLiteral.has(change.id) || findings.some((entry) => entry.factIds?.includes(change.id))) continue;
    // Reaction form: the name plus a body/behaviour change, no numbers.
    for (const sentence of sentences) {
      if (!mentions(sentence.narration, change.name, names)) continue;
      if (!hasAny(sentence.narration, BODY_REACTION) || !hasAny(sentence.narration, CHANGE_MARKERS)) continue;
      sanityReaction.add(change.id);
      findings.push(finding(ctx, 'review.natural_sanity', sentence.text,
        `${change.name}: sanity change shown through a reaction instead of the settled numbers; requires reading`,
        [`${change.name} 精神值：${change.from} → ${change.to}`], [change.id]));
      break;
    }
  }
  for (const change of projection.sanityChanges) {
    if (sanityLiteral.has(change.id) || sanityReaction.has(change.id)) continue;
    if (findings.some((entry) => entry.kind === 'fact.wrong_number' && entry.factIds?.includes(change.id))) continue;
    if (text.includes(change.name)) {
      findings.push(finding(ctx, 'review.tone', sentences[0]?.text ?? text,
        `${change.name}: the settled sanity change is not stated literally; the reaction needs reading`,
        [`${change.name} 精神值：${change.from} → ${change.to}`], [change.id]));
      continue;
    }
    findings.push(finding(ctx, 'fact.sanity_omitted', sentences[0]?.text ?? text,
      `${change.name}: ${change.from} → ${change.to} is not narrated`,
      [`${change.name} 精神值：${change.from} → ${change.to}`], [change.id]));
  }

  // ---------------------------------------------------------------- tasks
  const taskLiteral = new Set<string>();
  for (const task of projection.taskCompleted) {
    for (const sentence of sentences) {
      if (!sentence.text.includes(task.goal)) continue;
      const completion = hasAny(sentence.text, COMPLETION_VERBS);
      if (!completion) {
        findings.push(finding(ctx, 'review.tone', sentence.text,
          `goal quoted without a completion statement; status is ambiguous`, [task.goal], [task.id]));
        continue;
      }
      if (mentions(sentence.narration, task.name, names)) {
        taskLiteral.add(task.id);
      } else {
        const others = nameHits(sentence.narration, names, Object.keys(projection.people)).filter((hit) => hit.name !== task.name);
        if (others.length) {
          findings.push(finding(ctx, 'fact.actor_swap', sentence.text,
            `${task.name}'s completed task is attributed to ${others.map((hit) => hit.name).join('/')}`,
            [`${task.name} 完成：${task.goal}`], [task.id]));
        } else {
          findings.push(finding(ctx, 'review.pronoun', sentence.text,
            `completed task has no explicit actor; binding needs reading`, [task.goal], [task.id]));
        }
      }
      break;
    }
    if (taskLiteral.has(task.id)) continue;
    if (findings.some((entry) => entry.factIds?.includes(task.id))) continue;
    const tokens = goalTokens(task.goal);
    const result = !options.strict && text.includes(task.name)
      ? (sentences.find((sentence) => GOAL_COMPLETION.test(sentence.text)) ?? sentences[0])
      : sentences.find((sentence) => GOAL_COMPLETION.test(sentence.text)
        && tokens.filter((token) => sentence.text.includes(token)).length >= 2);
    if (result) {
      findings.push(finding(ctx, 'review.tone', result.text,
        `${task.name}'s result may be described without the frozen goal; content and actor need reading`,
        [task.goal], [task.id]));
      continue;
    }
    findings.push(finding(ctx, 'fact.task_omitted', sentences[0]?.text ?? text,
      `${task.name}: 「${task.goal}」 is not narrated as completed`, [`${task.name} 完成：${task.goal}`], [task.id]));
  }
  // A completed task written as still pending.
  for (const task of projection.taskCompleted) {
    for (const sentence of sentences) {
      if (!sentence.narration.includes(task.goal)) continue;
      if (/(还没|尚未|没有)(办完|做完|完成)|仍未完成/u.test(sentence.narration)) {
        findings.push(finding(ctx, 'fact.actor_swap', sentence.text,
          `${task.name}'s completed task is described as unfinished`, [task.goal], [task.id]));
      }
    }
  }

  // ---------------------------------------------------------- personality
  const personalityLiteral = new Set<string>();
  const personalityReaction = new Set<string>();
  for (const change of projection.personalityAdded) {
    for (const sentence of sentences) {
      if (sentence.text.includes(change.text)) {
        if (mentions(sentence.narration, change.name, names)) {
          personalityLiteral.add(change.id);
          break;
        }
        // The text can sit in the next sentence after a pronoun subject.
        const paragraph = sentences.filter((entry) => entry.paragraph === sentence.paragraph);
        if (paragraph.some((entry) => mentions(entry.narration, change.name, names))) {
          personalityLiteral.add(change.id);
          findings.push(finding(ctx, 'review.pronoun', sentence.text,
            `${change.name}'s new personality text is in a sentence without the name; actor binding needs reading`,
            [change.text], [change.id]));
          break;
        }
      }
    }
    if (personalityLiteral.has(change.id)) continue;
    for (const sentence of sentences) {
      if (!mentions(sentence.narration, change.name, names)) continue;
      if (!hasAny(sentence.narration, BODY_REACTION) || !hasAny(sentence.narration, CHANGE_MARKERS)) continue;
      personalityReaction.add(change.id);
      findings.push(finding(ctx, 'review.tone', sentence.text,
        `${change.name}: personality change shown through behaviour, not the settled text; requires reading`,
        [change.text], [change.id]));
      break;
    }
  }
  for (const change of projection.personalityAdded) {
    if (personalityLiteral.has(change.id) || personalityReaction.has(change.id)) continue;
    if (text.includes(change.name)) {
      findings.push(finding(ctx, 'review.tone', sentences[0]?.text ?? text,
        `${change.name}: the new personality is not stated literally; the behaviour needs reading`,
        [change.text], [change.id]));
      continue;
    }
    findings.push(finding(ctx, 'fact.personality_omitted', sentences[0]?.text ?? text,
      `${change.name}: new personality 「${change.text}」 is not narrated`, [change.text], [change.id]));
  }

  // A settled trait belongs to its person. Writing P's trait onto Q is a fact
  // error even when the words are copied verbatim from the state.
  {
    const owners = new Map<string, Set<string>>();
    for (const [name, person] of Object.entries(projection.people)) {
      for (const trait of person.personalityAfter) {
        if (trait.length < 4) continue;
        const set = owners.get(trait) ?? new Set<string>();
        set.add(name);
        owners.set(trait, set);
      }
    }
    const foreign = (name: string, trait: string): boolean => {
      if (!owners.has(trait) || owners.get(trait)!.has(name)) return false;
      return !(projection.people[name]?.personalityAfter ?? []).some((own) => own.includes(trait) || trait.includes(own));
    };
    for (const sentence of sentences) {
      const narration = sentence.narration;
      for (const name of Object.keys(projection.people)) {
        for (const hit of nameHits(narration, [name])) {
          const window = narration.slice(hit.index, hit.index + name.length + 24);
          if (!/的个性(?:是|就是|偏向|属于)|的性格(?:是|就是|偏向)/u.test(window)) continue;
          for (const [trait, who] of owners) {
            if (!foreign(name, trait)) continue;
            if (!sharesRun(window, trait, 4)) continue;
            findings.push(finding(ctx, 'fact.trait_misattribution', sentence.text,
              `${name} is given 「${trait}」, which belongs to ${[...who].join('/')}`,
              [trait], [`trait:${[...who][0]}:${trait}`]));
          }
        }
      }
      // Copying several settled traits into one sentence is a field recital even
      // when each owner is right.
      const copied = [...owners.keys()].filter((trait) => sharesRun(narration, trait, 4));
      if (copied.length >= 2) {
        findings.push(finding(ctx, 'review.personality_recital', sentence.text,
          `the sentence copies ${copied.length} settled personality strings; whether the behaviour is shown or only recited needs reading`,
          copied, []));
      }
    }
  }

  // Track the last person named before each sentence so a bare pronoun can be
  // read as that person when only one candidate exists.
  const lastPersonBefore = new Map<number, string | null>();
  {
    let lastPerson: string | null = null;
    sentences.forEach((sentence, index) => {
      lastPersonBefore.set(index, lastPerson);
      const hits = nameHits(sentence.narration, names, Object.keys(projection.people));
      if (hits.length) lastPerson = hits[hits.length - 1].name;
    });
  }
  const refersTo = (sentenceText: string, index: number, personName: string, strict = false): boolean => {
    if (sentenceText.includes(personName)) return true;
    if (!strict && projection.viewpoint === personName && !nameHits(sentenceText, names, Object.keys(projection.people)).length) return true;
    return /(他|她)/u.test(sentenceText) && lastPersonBefore.get(index) === personName;
  };

  // A settled look that this turn removed must not reappear as current.
  {
    const PAST = /(从前|原先|先前|早先|原来|以前|原本|曾|旧|本来|修好|补上|不再|没有|没再|漏过|过去)/u;
    // A removal is a transition: showing the earlier value and then the change
    // is allowed; only presenting the removed value as still current is an error.
    const TRANSITION = /(干|空|净|见底|没|少|浅|淡|消失|散|补|垫|修|换|擦|扫|倒|喝|收|合|关|灭|停)/gu;
    for (const removed of projection.appearanceRemoved) {
      if (removed.text.length < 4) continue;
      for (const [index, sentence] of sentences.entries()) {
        if (PAST.test(sentence.narration)) continue;
        const size = Math.min(6, removed.text.length);
        let fragmentAt = -1;
        for (let at = 0; at + size <= removed.text.length; at += 1) {
          const fragment = removed.text.slice(at, at + size);
          const found = sentence.narration.indexOf(fragment);
          if (found >= 0) { fragmentAt = found; break; }
        }
        if (fragmentAt < 0) continue;
        // Old value then a change (water that decreases, a seam that dries) is a
        // transition; the removed value after the change is a contradiction.
        const sentenceAt = text.indexOf(sentence.text);
        const absolute = sentenceAt >= 0 ? sentenceAt + Math.max(0, fragmentAt) : -1;
        const after = absolute >= 0 && [...text.slice(absolute).matchAll(TRANSITION)].some((match) => (match.index ?? 0) > 0);
        if (after) continue;
        findings.push(finding(ctx, 'fact.state_contradiction', sentence.text,
          `${removed.entity}: 「${removed.text}」 was removed this turn but is narrated as still true`,
          [removed.text], [removed.id]));
      }
    }
  }

  // ---------------------------------------------------------------- items
  const itemStateCovered = new Set<string>();
  for (const sentence of sentences) {
    const narration = sentence.narration;
    for (const [object, holder] of ctx.holders.holders) {
      const clause = possessionClause(narration, object);
      if (!clause) continue;
      const personHits = nameHits(clause, names, Object.keys(projection.people));
      const claimers = personHits.map((hit) => hit.name);
      let implied = projection.viewpoint && !claimers.length ? [projection.viewpoint] : claimers;
      if (!claimers.length) {
        const before = narration.slice(0, Math.max(0, narration.indexOf(clause)));
        const unique = [...new Set(nameHits(before, names, Object.keys(projection.people)).map((hit) => hit.name))];
        const pronounLocative = /(?:他|她|他们|她们)(?:手里|手中|肩上|背上|怀里|胸前|脖子上|腰间)/u.test(clause);
        if (unique.length === 1 && (/^\s*(?:他|她|他们|她们|手里|手中|肩上|背上|怀里|胸前|脖子上|腰间)/u.test(clause) || pronounLocative)) implied = unique;
      }
      if (holder === 'scene') {
        // Carrying it from A to B is licensed when the object and a person
        // both moved A -> B in this point.
        const itemMove = projection.moves.find((move) => move.kind === 'item' && move.name === object);
        const sentencePeople = nameHits(narration, names, Object.keys(projection.people)).map((hit) => hit.name);
        const carrier = itemMove
          ? projection.moves.find((move) => move.kind === 'person' && move.from === itemMove.from && move.to === itemMove.to
              && (sentencePeople.includes(move.name) || claimers.includes(move.name)))
          : undefined;
        if (carrier) continue;
        findings.push(finding(ctx, 'review.micro_action', sentence.text,
          `${object} is settled in the scene (${ctx.holders.basis.get(object)}) and is written as held; picking it up changes no settled end state`,
          [ctx.holders.basis.get(object) ?? ''], [`item:${object}`]));
        continue;
      }
      if (implied.length && !implied.includes(holder)) {
        findings.push(finding(ctx, 'fact.item_misattribution', sentence.text,
          `${object} belongs with ${holder}, not ${implied.join('/')}`,
          [ctx.holders.basis.get(object) ?? ''], [`item:${object}`]));
        continue;
      }
      if (!implied.length) {
        findings.push(finding(ctx, 'review.pronoun', sentence.text,
          `${object}: holder is not named; binding needs reading`, [ctx.holders.basis.get(object) ?? '']));
      }
    }
    // A settled appearance that says the hand is empty contradicts any
    // possession claim by that person in the same sentence.
    for (const person of Object.values(projection.people)) {
      const emptyHand = person.appearanceAfter.find((entry) => /(手|右手|左手)[^。]{0,4}空着/u.test(entry));
      if (!emptyHand) continue;
      const named = mentions(narration, person.name, names);
      const impliedViewpoint = projection.viewpoint === person.name && !nameHits(narration, names, Object.keys(projection.people)).length;
      if (!named && !impliedViewpoint) continue;
      const handled = (entry: string): string | null => {
        const clause = possessionClause(narration, entry);
        if (clause) return clause;
        const index = narration.indexOf(entry);
        if (index < 0) return null;
        const around = clauseAt(narration, index).text;
        if (!hasAny(around, HANDLING_VERBS)) return null;
        // Wearing something is not holding it.
        if (/(挂在|戴在|别在)[^，。]{0,5}(胸前|身上|颈|脖子|肩|腰|头发)/u.test(around)) return null;
        const settled = Object.entries(projection.items)
          .filter(([name]) => name.includes(entry) || entry.includes(name.replace(/^.*的/u, '')))
          .flatMap(([, item]) => item.descriptions);
        if (settled.some((text) => sharesRun(around, text, 4))) return null;
        return around;
      };
      const prop = [...ctx.holders.holders.keys()].find((entry) => handled(entry))
        ?? PROPS.find((entry) => handled(entry));
      if (!prop) continue;
      // Picking a settled scene object up is polish; only a prop with no
      // settled place (or one that belongs to someone else) is a fact error.
      const propHolder = [...ctx.holders.holders.entries()].find(([name]) => name === prop || prop.includes(name))?.[1];
      if (propHolder === 'scene') continue;
      const verb = hasAny(handled(prop) ?? '', POSSESSION_VERBS)
        ?? hasAny(handled(prop) ?? '', HANDLING_VERBS);
      if (!verb) continue;
      findings.push(finding(ctx, 'fact.item_misattribution', sentence.text,
        `${person.name}'s settled appearance says the hand is empty, but the prose has ${prop} in it`,
        [emptyHand], [`item:${prop}`]));
    }
    // Invented concrete objects: absent from the input, yet handled or claimed
    // as the contents of a settled container.
    for (const noun of INVENTABLE_OBJECTS) {
      if (!narration.includes(noun)) continue;
      if (projection.sourceText.includes(noun)) continue;
      // A compound whose head noun is settled ("箱子" when the state says 箱)
      // is the same object, not an invention.
      const head = [...noun].slice(0, 2).join('');
      const headLicensed = [...head].length === 2 && projection.sourceText.includes(head);
      if (headLicensed) continue;
      const index = narration.indexOf(noun);
      if (negatedAt(narration, noun)) continue;
      if (/(?:像|仿佛|如同|似的)[^。]{0,4}$/u.test(narration.slice(0, index))) {
        findings.push(finding(ctx, 'review.object_added', sentence.text,
          `${noun} appears only inside a simile; needs reading`, [], []));
        continue;
      }
      const window = narration.slice(Math.max(0, index - 8), index + noun.length + 8);
      const handled = ITEM_HANDLING_VERBS.some((verb) => window.includes(verb))
        || ITEM_STATE_VERBS.some((verb) => window.includes(verb));
      const containerClaim = /(?:里面|里|中|内)(?:是|放着|装着|有|多出|躺着)/u.test(window);
      const rootChar = [...noun][0] ?? '';
      const rootLicensed = rootChar.length === 1 && projection.sourceText.includes(rootChar);
      if ((handled || containerClaim) && rootLicensed) {
        findings.push(finding(ctx, 'review.object_added', sentence.text,
          `${noun} may be a renamed settled object (the state has ${rootChar}); needs reading`, [], []));
        continue;
      }
      if (handled || containerClaim) {
        findings.push(finding(ctx, 'fact.object_added', sentence.text,
          `${noun} is not in the settled state and is ${handled ? 'handled' : 'claimed as container content'}`,
          [], []));
        continue;
      }
      findings.push(finding(ctx, 'review.object_added', sentence.text,
        `${noun} is not in the settled state; inert detail needs reading`, [], []));
    }
    // Item state verbs on known objects need a settled item change.
    for (const verb of ITEM_STATE_VERBS) {
      if (!narration.includes(verb)) continue;
      if (negatedAt(narration, verb)) continue;
      const clause = clauseAt(narration, narration.indexOf(verb)).text;
      const object = [...ctx.holders.holders.keys()].find((entry) => clause.includes(entry))
        ?? PROPS.find((entry) => clause.includes(entry));
      if (!object) continue;
      if (ctx.stateLicensed(verb)) {
        itemStateCovered.add(object);
        continue;
      }
      // A completed task is settled evidence that the action it names happened.
      if (projection.taskCompleted.some((task) => sentence.text.includes(task.goal))) {
        itemStateCovered.add(object);
        continue;
      }
      // Only a settled item can be contradicted. An invented prop (a key that
      // was never in the state) is a micro-detail for review, not a fact error.
      if (ITEM_HANDLING_VERBS.includes(verb as typeof ITEM_HANDLING_VERBS[number])) {
        const handler = nameHits(clause, names, Object.keys(projection.people)).length > 0
          || /(他|她|手|指尖|指头)/u.test(clause);
        if (!handler) continue;
        findings.push(finding(ctx, 'review.micro_action', sentence.text,
          `${object}: ${verb} moves the object between hands; no settled state is contradicted`, [], [`item:${object}`]));
        continue;
      }
      const knownItem = object in projection.items
        || projection.itemDescriptions.some((entry) => entry.includes(object))
        || Object.values(projection.people).some((person) => person.appearanceAfter.some((entry) => entry.includes(object)));
      if (!knownItem) {
        findings.push(finding(ctx, 'review.micro_action', sentence.text,
          `${object} is not a settled item; the state change (${verb}) is an invented prop detail`, [], []));
        continue;
      }
      const settledChange = projection.appearanceAdded.some((entry) => entry.entity === object)
        || projection.appearanceRemoved.some((entry) => entry.entity === object)
        || projection.moves.some((move) => move.kind === 'item' && move.name === object);
      if (settledChange) {
        itemStateCovered.add(object);
        continue;
      }
      if (sentence.quotes.length && !sentence.narration.replace(/「」/gu, '').includes(verb)) {
        findings.push(finding(ctx, 'review.speech_act', sentence.text,
          `${object}: the state change (${verb}) is only planned or said, not narrated`, [], [`item:${object}`]));
        continue;
      }
      findings.push(finding(ctx, 'fact.event_added', sentence.text,
        `${object} changes state (${verb}) with no settled change`, [], [`item:${object}`]));
    }
  }

  // --------------------------------------------------------------- events
  for (const sentence of sentences) {
    const narration = sentence.narration;
    for (const verb of EVENT_VERBS) {
      if (!narration.includes(verb)) continue;
      if (verbLicensed(verb, ctx, narration)) continue;
      // Already reported as an item-state issue.
      if (ITEM_STATE_VERBS.includes(verb as typeof ITEM_STATE_VERBS[number])
        && PROPS.some((prop) => narration.includes(prop))) continue;
      if (sentence.quotes.length && !narration.replace(/「」/gu, '').includes(verb)) {
        findings.push(finding(ctx, 'review.speech_act', sentence.text,
          `the event verb ${verb} appears only inside dialogue`, [], []));
        continue;
      }
      findings.push(finding(ctx, 'fact.event_added', sentence.text,
        `event verb ${verb} has no settled fact and no settled description`, [], []));
    }
    for (const place of Object.keys(projection.places)) {
      const towards = new RegExp(`(?:往|朝|向)${escapeRegExp(place)}(?:那边|这边|方向)?(?:走|去|跑|挪)`, 'u');
      if (!towards.test(narration)) continue;
      const actor = nameHits(narration, names, Object.keys(projection.people))[0]?.name ?? null;
      const licensed = actor
        ? projection.moves.some((move) => move.kind === 'person' && move.name === actor && move.to === place)
        : false;
      if (!licensed) {
        findings.push(finding(ctx, 'fact.event_added', sentence.text,
          `movement towards ${place} has no settled move fact`, [], actor ? [`move:${actor}`] : []));
      }
    }
    for (const verb of SOFT_EVENT_VERBS) {
      if (!narration.includes(verb)) continue;
      if (verbLicensed(verb, ctx, narration)) continue;
      if (ctx.stateLicensed(verb)) continue;
      // Only a person or a reaching body part can handle something; 照在盒盖上
      // is not someone touching the lid.
      const handlingActor = nameHits(narration, names, Object.keys(projection.people)).length > 0
        || /(他|她|手|指尖|指头)/u.test(narration);
      if (!handlingActor) continue;
      findings.push(finding(ctx, 'review.micro_action', sentence.text,
        `physical handling (${verb}) with no settled fact; allowed as a micro-action when it changes no settled state`, [], []));
    }
    const soundForms = [
      ...SOUND_WORDS.filter((sound) => narration.includes(sound)),
      ...[...narration.matchAll(/(?:摩擦|撞击|碎裂|爆裂|沙沙|嗡嗡|低语|呼喊)的(?:声响|声音|动静)/gu)].map((match) => match[0]),
    ];
    for (const sound of soundForms) {
      if (!narration.includes(sound)) continue;
      if (negatedAt(narration, sound)) continue;
      if (ctx.stateLicensed(sound)) continue;
      // A footstep needs a mover named in this sentence, not merely a move
      // somewhere in the point: the text may still put that mover elsewhere.
      const movedHere = MOVE_VERBS.some((verb) => narration.includes(verb) && !negatedAt(narration, verb));
      const moverHere = movedHere && projection.moves.some((move) => move.kind === 'person' && narration.includes(move.name));
      if (sound === '脚步声' && moverHere) continue;
      // Ambient sounds of a settled action (a door the text says opened, an
      // object the text says was handled) are licensed by that action.
      const actionHere = ITEM_STATE_VERBS.some((verb) => narration.includes(verb) && !negatedAt(narration, verb))
        || HANDLING_VERBS.some((verb) => narration.includes(verb) && !negatedAt(narration, verb))
        || MOVE_VERBS.some((verb) => narration.includes(verb) && moverHere);
      if (actionHere && sound !== '脚步声') continue;
      findings.push(finding(ctx, 'fact.sound_added', sentence.text,
        `${sound} has no settled source`, [], []));
    }
    for (const marker of PAST_MARKERS) {
      if (!narration.includes(marker)) continue;
      if (ctx.stateLicensed(marker)) continue;
      const comparesToChange = [...projection.appearanceAdded, ...projection.appearanceRemoved]
        .some((entry) => sharesRun(narration, entry.text, 4));
      if (comparesToChange) {
        findings.push(finding(ctx, 'review.tone', sentence.text,
          `past comparison ${marker} is tied to a settled change; wording needs reading`, [], []));
        continue;
      }
      findings.push(finding(ctx, 'fact.past_added', sentence.text,
        `past reference ${marker} has no settled basis`, [], []));
    }
    for (const verb of PROMISE_VERBS) {
      if (!narration.includes(verb)) continue;
      if (ctx.stateLicensed(verb)) continue;
      if (negatedAt(narration, verb)) continue;
      findings.push(finding(ctx, 'fact.promise_added', sentence.text,
        `promise verb ${verb} has no settled basis`, [], []));
    }
    // A settled habit or conditional reaction is not a current event.
    for (const entry of settledStrings) {
      if (!CONDITIONAL.test(entry)) continue;
      const reaction = /(?:会|就|便)([^，。；]{2,10})/u.exec(entry);
      const trigger = /(?:听见|听到|看见|看到|遇到|若|如果)([^，。；]{2,10}?)(?:会|就|便)/u.exec(entry);
      if (!reaction) continue;
      const reactionText = reaction[1].trim();
      const reactionVerb = reactionText.replace(/^(?:下意识|不自觉|忍不住|总是|常常)/u, '').slice(-3);
      if (!reactionVerb || !narration.includes(reactionVerb)) continue;
      const triggerWord = trigger ? trigger[1].replace(/[的地得].*$/u, '').trim().slice(-2) : '';
      const triggerHere = !!triggerWord && narration.includes(triggerWord);
      if (!triggerHere) {
        findings.push(finding(ctx, 'review.trait_as_event', sentence.text,
          `settled habit 「${entry}」 is written as a current reaction; trigger is missing, wording needs reading`, [entry], []));
        continue;
      }
      findings.push(finding(ctx, 'fact.trait_as_event', sentence.text,
        `settled habit 「${entry}」 is written as an event happening now (${triggerWord} + ${reactionVerb})`, [entry], []));
    }
    // A static object or place cannot speak or sound by itself.
    const spokenObjects = new Set<string>();
    const SPEECH = /(说|喊|叫|提醒|念|广播|发出|传来)/gu;
    for (const [objectName, holder] of ctx.holders.holders) {
      if (holder !== 'scene') continue;
      const objectIndex = narration.indexOf(objectName);
      if (objectIndex < 0) continue;
      let spoken: string | null = null;
      for (const match of narration.matchAll(SPEECH)) {
        const verb = match[1];
        const verbIndex = match.index ?? 0;
        // A person in the same breath is the speaker, not the object.
        const before = narration.slice(Math.max(0, verbIndex - 10), verbIndex);
        if (OBJECT_SPEAKER_NAMES.some((name) => before.includes(name))) continue;
        if (/(没有|没|未|别|再|先|像|仿佛|似乎|要)$/u.test(before)) continue;
        const distance = Math.abs(verbIndex - (objectIndex + objectName.length));
        if (distance > 8 && Math.abs(verbIndex - objectIndex) > 8) continue;
        // A comma or a quote between them means another clause owns the verb.
        const between = narration.slice(Math.min(objectIndex + objectName.length, verbIndex), Math.max(objectIndex, verbIndex));
        if (/[，。；、」「]/u.test(between)) continue;
        spoken = verb;
        break;
      }
      if (!spoken) continue;
      const identity = ctx.holders.basis.get(objectName) ?? objectName;
      if (spokenObjects.has(identity)) continue;
      spokenObjects.add(identity);
      findings.push(finding(ctx, 'fact.object_speaks', sentence.text,
        `${objectName} is a settled object and cannot ${spoken} by itself`, [identity], []));
    }
    // A passive past event ("被弹片击中") needs a settled basis.
    const passive = /(?:被[^，。；]{0,8}(?:击中|打中|撞到|推倒|割伤|压住|拖走)|(?:弹片|碎屑|碎片|玻璃)[^，。；]{0,6}(?:刮|划|擦|击|打)(?:过|中|到|伤))/u.exec(narration);
    if (passive && !ctx.stateLicensed(passive[1] ?? passive[0])) {
      findings.push(finding(ctx, 'fact.past_added', sentence.text,
        `passive past event ${passive[0]} has no settled basis`, [], []));
    }
    // A person claimed at a settled place that is not where they stand.
    {
      const placeNames = Object.keys(projection.places).sort((a, b) => b.length - a.length);
      const peopleNames = Object.keys(projection.people);
      const actorOf = (claimIndex: number, markerLength: number): string | null => {
        const window = narration.slice(Math.max(0, claimIndex - 12), claimIndex + markerLength);
        let best: { name: string; at: number } | null = null;
        for (const candidate of peopleNames) {
          const at = window.lastIndexOf(candidate);
          if (at >= 0 && (!best || at >= best.at)) best = { name: candidate, at };
        }
        if (best) return best.name;
        if (projection.viewpoint && /(他|她|自己)/u.test(window)) return projection.viewpoint;
        return null;
      };
      for (const [personName, person] of Object.entries(projection.people)) {
        const settledPlace = basePlace(person.positionAfter ?? person.positionBefore);
        if (!settledPlace) continue;
        const direction = /(?:在|站在|走到|来到|到了)(东|西|南|北)侧/u.exec(narration);
        if (direction && /^[东西南北中]/u.test(settledPlace) && settledPlace[0] !== direction[1]
          && actorOf(direction.index, direction[0].length) === personName) {
          findings.push(finding(ctx, 'fact.wrong_place', sentence.text,
            `${personName} is settled at ${settledPlace}; the prose puts them on the ${direction[1]} side`, [settledPlace], []));
          continue;
        }
        for (const place of placeNames) {
          if (place === settledPlace) continue;
          const claim = new RegExp(`(在|站在|坐在|蹲在|靠在|留在|待在|回到|来到|走进|走回|进了)${place}`, 'u').exec(narration);
          if (!claim) continue;
          // 「浮标还搁在工具棚」 is an object state, not a person standing there.
          if (claim[1] === '在' && /[搁放挂摆压贴插藏塞停摊晾悬留]/u.test(narration[claim.index - 1] ?? '')) continue;
          // A gaze or an object reaching a place is not the person standing there.
          if (/(视线|目光|眼神|余光|影子|声音|脚步声|手|脚)$/u.test(narration.slice(Math.max(0, claim.index - 3), claim.index))) continue;
          if (actorOf(claim.index, claim[1].length) !== personName) continue;
          if (projection.moves.some((move) => move.kind === 'person' && move.name === personName && move.to === place)) continue;
          const departing = /(从|离开|走出|下去|上来)/u.test(narration);
          if (departing && projection.moves.some((move) => move.kind === 'person' && move.name === personName && move.from === place)) continue;
          const settledInside = settledPlace.startsWith(place) && settledPlace !== place;
          if (settledInside) {
            findings.push(finding(ctx, 'fact.wrong_place', sentence.text,
              `${personName} is settled inside ${settledPlace}; the prose puts them at the outer ${place}`, [settledPlace], []));
            break;
          }
          if (!place.startsWith(settledPlace)) {
            findings.push(finding(ctx, 'fact.wrong_place', sentence.text,
              `${personName} is settled at ${settledPlace}; the prose puts them at ${place}`, [settledPlace], []));
            break;
          }
        }
      }
    }
    // A body mark (red weal, blood, bruise) on a named body part must exist in
    // the settled appearance; otherwise it is a new physical fact.
    // A settled look in the sentence identifies whose body is described. When
    // none is present, the mark needs an explicit name or pronoun: the
    // viewpoint fallback would pin a copied description of someone else onto
    // the player.
    const namedHere = nameHits(narration, names, Object.keys(projection.people)).length > 0;
    const lookOwner = namedHere ? null : (Object.entries(projection.people).find(([, person]) =>
      person.appearanceAfter.some((look) => look.length >= 3 && sharesRun(narration, look, 3)))?.[0] ?? null);
    for (const [personName, person] of Object.entries(projection.people)) {
      if (lookOwner ? lookOwner !== personName : !refersTo(narration, sentences.indexOf(sentence), personName, namedHere)) continue;
      const mark = /(红痕|血迹|流血|伤口|淤青|擦伤|疤痕|肿起|肿了|绷带|包扎)/u.exec(narration);
      if (!mark) continue;
      const nearby = narration.slice(Math.max(0, mark.index - 25), mark.index + mark[1].length);
      const body = /(手背|手心|手指|手腕|手臂|胳膊|大臂|小臂|右臂|左臂|膝盖|小腿|脚踝|额头|脸|脸颊|肩膀|后背|脖子|颈侧)/u.exec(nearby);
      if (!body) continue;
      const settled = [...person.appearanceAfter, ...person.appearanceBefore].join('｜');
      if (settled.includes(mark[1])) continue;
      findings.push(finding(ctx, 'fact.body_mark_added', sentence.text,
        `${personName}: ${body[1]} has ${mark[1]} in the prose but not in the settled appearance`, [settled.slice(0, 40)], []));
      break;
    }
    // A mark settled on one side of the body cannot move to the other side.
    for (const [personName, person] of Object.entries(projection.people)) {
      const settledLooks = [...person.appearanceAfter, ...person.appearanceBefore].join('｜');
      const sideOf = (textValue: string): { side: string; mark: string } | null => {
        const mark = /(红痕|血迹|伤口|淤青)/u.exec(textValue);
        if (!mark) return null;
        const before = textValue.slice(Math.max(0, mark.index - 7), mark.index);
        const left = /([左右])(?:袖|臂|肩|手|腿|脚)[^。；，]{0,4}$/u.exec(before);
        if (left) return { side: left[1], mark: mark[1] };
        const after = textValue.slice(mark.index + mark[1].length, mark.index + mark[1].length + 7);
        const right = /^[^。；，]{0,4}([左右])(?:袖|臂|肩|手|腿|脚)/u.exec(after);
        return right ? { side: right[1], mark: mark[1] } : null;
      };
      const settledSide = sideOf(settledLooks);
      if (!settledSide) continue;
      const proseSide = sideOf(narration);
      if (!proseSide || proseSide.side === settledSide.side) continue;
      if (!refersTo(narration, sentences.indexOf(sentence), personName)) continue;
      findings.push(finding(ctx, 'fact.state_contradiction', sentence.text,
        `${personName}: the ${proseSide.mark} is settled on the ${settledSide.side} side but the prose puts it on the ${proseSide.side} side`, [settledLooks.slice(0, 40)], []));
      break;
    }
    // A settled appearance can be contradicted by its opposite direction.
    const settledLooks = [
      ...Object.values(projection.people).flatMap((person) => person.appearanceAfter),
      ...Object.values(projection.items).flatMap((item) => item.descriptions),
    ];
    for (const look of settledLooks) {
      if (!/枪口[^。]{0,4}(压向地面|朝下|向下|对着地面)/u.test(look)) continue;
      if (!/(抬起|朝上|指向天空|指向屋顶)/u.test(narration)) continue;
      findings.push(finding(ctx, 'fact.state_contradiction', sentence.text,
        `settled appearance says ${look.slice(0, 24)}; the prose turns the muzzle up`, [look], []));
      break;
    }
    // A place the viewpoint cannot see (outside its own location) being looked at.
    if (options.strict !== false) {
      for (const place of Object.keys(projection.places)) {
        if (!narration.includes(place)) continue;
        const sight = /(望着|看着|看见|望向|望见|看向)[^，。]{0,6}$/u.test(narration.slice(0, narration.indexOf(place)));
        if (!sight) continue;
        const viewpointPlace = projection.viewpoint
          ? projection.people[projection.viewpoint]?.positionAfter ?? projection.people[projection.viewpoint]?.positionBefore ?? null
          : null;
        const inside = viewpointPlace ? place === viewpointPlace || projection.places[place]?.parent === viewpointPlace : false;
        if (inside) continue;
        findings.push(finding(ctx, 'review.unseen_entity', sentence.text,
          `${place} is outside the viewpoint's location; whether it is visible needs reading`, [], []));
        break;
      }
    }
    if (projection.viewpoint) {
      for (const hit of nameHits(narration, names, Object.keys(projection.people))) {
        if (hit.name === projection.viewpoint) continue;
        const tail = narration.slice(hit.index + hit.name.length);
        const next = nameHits(tail, names, Object.keys(projection.people))
          .filter((other) => other.name !== hit.name)
          .map((other) => other.index)
          .sort((a, b) => a - b)[0];
        const scope = next === undefined ? tail : tail.slice(0, next);
        const interior = hasAny(scope, INTERIOR);
        if (interior && new RegExp(`(?:不知道|没|未|不曾)[^，。]{0,3}${escapeRegExp(interior)}`, 'u').test(scope)) continue;
        if (interior) {
          findings.push(finding(ctx, 'fact.viewpoint_interiority', sentence.text,
            `${hit.name} is narrated with interiority (${interior}) outside ${projection.viewpoint}'s viewpoint`,
            [], [`viewpoint:${projection.viewpoint}`]));
        }
      }
    }
    for (const secret of options.mustNotReveal ?? []) {
      if (secret.length >= 2 && text.includes(secret)) {
        findings.push(finding(ctx, 'fact.knowledge_leak', sentence.text,
          `hidden knowledge surfaced: ${secret}`, [secret]));
      }
    }
    for (const unseen of options.unseenEntities ?? []) {
      if (unseen.length >= 2 && sentence.text.includes(unseen)) {
        findings.push(finding(ctx, 'fact.knowledge_leak', sentence.text,
          `${unseen} is not perceivable from the viewpoint yet`, [unseen]));
      }
    }
  }

  // -------------------------------------------------------------- gender
  const bound = pronounBindings(sentences, names, Object.keys(projection.people), options.genders);
  const genderByAntecedent = new Map<string, Set<'male' | 'female'>>();
  for (const binding of bound) {
    const sentence = sentences[binding.sentence];
    if (binding.strength === 'ambiguous') {
      if (binding.candidates.length >= 1) {
        findings.push(finding(ctx, 'review.pronoun', sentence.text,
          `${binding.pronoun}: the antecedent is ambiguous (candidates ${binding.candidates.join('/')}); a human must decide`,
          [], binding.candidates.map((name) => `person:${name}`)));
      }
      continue;
    }
    const antecedent = binding.antecedent as string;
    const set = genderByAntecedent.get(antecedent) ?? new Set();
    set.add(binding.gender);
    genderByAntecedent.set(antecedent, set);
    const registered = options.genders?.[antecedent];
    if (registered && registered !== binding.gender) {
      findings.push(finding(ctx, 'fact.gender', sentence.text,
        `${antecedent} is referred to as ${binding.pronoun} but the reviewed registry says ${registered === 'male' ? 'male' : 'female'}`,
        [`registry: ${antecedent}=${registered}`]));
    }
  }
  for (const [antecedent, genders] of genderByAntecedent) {
    if (genders.size < 2) continue;
    // Internal inconsistency is a review signal, not a verdict: Chinese
    // pronoun resolution can attribute wrongly, so a human must check.
    const sentence = sentences.find((entry, index) => bound.some((binding) => binding.antecedent === antecedent && binding.sentence === index));
    findings.push(finding(ctx, 'review.pronoun', sentence?.text ?? text,
      `${antecedent} is bound to both 他 and 她; at most one is right and the attribution needs reading`, []));
  }

  // -------------------------------------------------------------- style
  const normalized = sentences.map((entry) => normalize(entry.text)).filter((entry) => entry.length >= 6);
  const sentenceCounts = new Map<string, number>();
  for (const entry of normalized) sentenceCounts.set(entry, (sentenceCounts.get(entry) ?? 0) + 1);
  for (const [entry, count] of sentenceCounts) {
    if (count < 2) continue;
    findings.push(finding(ctx, 'style.loop', entry, `sentence repeated ${count} times`, []));
  }
  if (/。。|，，|、、|；；|：：/u.test(text)) {
    const hit = sentences.find((entry) => /。。|，，|、、|；；|：：/u.test(entry.text) || entry.text === '。');
    findings.push(finding(ctx, 'style.punctuation', hit?.text ?? text.slice(0, 40), 'duplicated punctuation', []));
  }
  let firstPersonSentence: string | null = null;
  for (const sentence of sentences) {
    const narration = sentence.narration;
    const spoken = /(说|问|答|道|喊|叫|想|觉得|认为|念叨|嘟囔)[^，。！？\s]{0,4}我/u.test(narration);
    if (!spoken && /(^|[，。！？；：、\s])我(?!们)/u.test(narration)) firstPersonSentence ??= sentence.text;
    // Name + several settled looks in one breath is the state panel written as
    // prose: the character is introduced by reciting the appearance fields.
    for (const [name, person] of Object.entries(projection.people)) {
      if (!refersTo(sentence.text, sentences.indexOf(sentence), name)) continue;
      const looks = person.appearanceAfter.filter((look) => look.length >= 4 && sharesRun(narration, look, 3));
      const posture = /(站在|坐在|靠在|蹲在|立在|在那里)/u.test(narration);
      if (looks.length >= 3 || (looks.length >= 2 && posture && projection.viewpoint === name)) {
        findings.push(finding(ctx, 'style.appearance_recital', sentence.text,
          `${name}: ${looks.length} settled appearance strings are listed in one sentence`,
          looks, []));
      }
    }
    const field = FIELD_WORDS.find((word) => sentence.narration.includes(word));
    if (field && /(精神|理智|任务|个性|外貌|状态)/u.test(sentence.text)) {
      findings.push(finding(ctx, 'style.field_sentence', sentence.text,
        `names a state field (${field}) inside prose`, []));
    }
    const panel = bareFieldSentence(sentence.text, projection);
    if (panel) findings.push(finding(ctx, 'style.status_panel', sentence.text, panel, []));
    const people = nameHits(sentence.narration, names, Object.keys(projection.people)).map((hit) => hit.name);
    if (new Set(people).size >= 3 && !hasAny(sentence.narration, EVENT_VERBS) && !hasAny(sentence.narration, MOVE_VERBS)) {
      findings.push(finding(ctx, 'style.roster_recital', sentence.text,
        `recites ${new Set(people).size} people in one place statement`, []));
    }
    if (/【[^】]{0,6}事实】|本拍|这一回合|本回合|回合结算|本组结算|结算未能确认|未能确认新的结果|系统|状态已|按已结算|程序成文|降级成文/u.test(sentence.text)) {
      findings.push(finding(ctx, 'style.meta', sentence.text, 'meta/game-system wording inside prose', []));
    }
  }
  if (firstPersonSentence !== null) {
    findings.push(finding(ctx, 'style.perspective', firstPersonSentence,
      'first-person prose outside dialogue; the viewpoint is a named person and the rows are third-person', []));
  }
  const bare = text.replace(/[\s。．，,、；;：:！!？?…·.．"“”‘’]/gu, '');
  if (charCount > 0 && bare.length === 0) {
    findings.push(finding(ctx, 'style.placeholder', sentences[0]?.text ?? text,
      'the text carries no words: only punctuation or an ellipsis was shown', []));
  }
  const last = sentences.at(-1)?.text.trim() ?? '';
  if (charCount >= 40 && !TERMINAL_PUNCTUATION.test(last)) {
    findings.push(finding(ctx, 'style.truncated', last, 'text does not end at a sentence boundary', []));
  }
  if (options.minChars !== undefined && charCount > 0 && charCount < options.minChars) {
    findings.push(finding(ctx, 'style.truncated', last, `${charCount} < ${options.minChars} characters`, []));
  }
  const target = options.targetChars;
  if (target && charCount > 0 && charCount < target * 0.6 && (CLOSURE.test(last) || FAREWELL.test(last))) {
    findings.push(finding(ctx, 'style.premature_closure', last, 'scene closes well before the target length', []));
  }
  for (const prior of options.priorTexts ?? []) {
    const opening = normalize(sentences[0]?.text ?? '');
    const priorOpening = normalize(splitSentences(prior)[0]?.text ?? '');
    if (opening.length >= 8 && opening === priorOpening) {
      findings.push(finding(ctx, 'style.repeated_opening', sentences[0]?.text ?? '',
        'the opening sentence is verbatim the same as a previous turn', []));
    }
    const overlap = bigramCoverage(text, prior);
    if (overlap > 0.5) {
      findings.push(finding(ctx, 'style.echo_prior', sentences[0]?.text ?? '',
        `bigram coverage against a previous turn is ${overlap.toFixed(2)}`, []));
    }
  }

  // --------------------------------------------------------- review items
  for (const sentence of sentences) {
    const narration = sentence.narration;
    const boundFacts = boundFactIds(sentence, projection, names, ctx);
    if (!boundFacts.length) {
      const action = hasAny(narration, EVENT_VERBS) ?? hasAny(narration, MOVE_VERBS)
        ?? hasAny(narration, POSTURE) ?? hasAny(narration, BODY_ACTIONS);
      if (action) {
        findings.push(finding(ctx, 'review.micro_action', sentence.text,
          `physical action (${action}) with no settled fact; allowed only as a micro-action`, []));
      } else if (sentence.quotes.length) {
        findings.push(finding(ctx, 'review.speech_act', sentence.text,
          'dialogue with no settled fact; content needs reading', []));
      } else if (charCount > 0) {
        findings.push(finding(ctx, 'review.tone', sentence.text,
          'no settled fact binds this sentence; it is atmosphere or inference', []));
      }
    }
    const posture = hasAny(narration, POSTURE);
    if (posture && boundFacts.length) {
      findings.push(finding(ctx, 'review.micro_action', sentence.text,
        `posture (${posture}) is not settled; allowed as a micro-action but not as state`, []));
    }
    // Unquoted speech is an event, not just wording: the reader needs a basis.
    const unquoted = hasAny(narration, SPEECH_VERBS_UNQUOTED);
    if (unquoted && !negatedAt(narration, unquoted) && !sentence.quotes.length) {
      findings.push(finding(ctx, 'review.speech_act', sentence.text,
        `narrated speech (${unquoted}) with no settled dialogue; the event and wording need reading`, []));
    }
    // Something is held, but the point gives no object for it.
    if (!boundFacts.length && /(?:手中|手里|掌心)[^，。]{0,4}(?:握着|拿着|攥着|端着|提着)/u.test(narration)
      && ![...ctx.holders.holders.values()].some((holder) => holder !== 'scene')) {
      findings.push(finding(ctx, 'review.possession', sentence.text,
        'a hand holds something, but the point settles no object for it', []));
    }
    // A promise or a future arrangement inside dialogue is a new commitment,
    // not wording: the reader will expect it to happen.
    for (const quote of sentence.quotes) {
      if (/(?:明天|后天|今晚|等我|我会|我保证|一定|回头|下次)/u.test(quote) && /(?:去|来|找|见|给|带|送|等)/u.test(quote)) {
        findings.push(finding(ctx, 'review.promise_in_dialogue', sentence.text,
          `dialogue makes an arrangement (${quote.slice(0, 16)}) that no settled fact supports`, []));
        break;
      }
    }
    for (const quote of sentence.quotes) {
      if (projection.sourceText.includes(quote)) continue;
      if (quote.length < 2) continue;
      if (!findings.some((entry) => entry.sentence === sentence.text && entry.kind === 'review.speech_act')) {
        findings.push(finding(ctx, 'review.speech_act', sentence.text,
          `dialogue content 「${quote.slice(0, 20)}」 needs a basis check`, []));
      }
    }
  }

  // ------------------------------------------------ sentence compilation
  sentences.forEach((sentence, index) => {
    const own = findings.filter((entry) => entry.sentence === sentence.text || entry.sentence === sentence.text.trim());
    const factIds = [...new Set(own.flatMap((entry) => entry.factIds ?? []))];
    const basis = [...new Set(own.flatMap((entry) => entry.basis))];
    const judgement = own.some((entry) => entry.severity === 'fact')
      ? 'fact_error'
      : own.some((entry) => entry.severity === 'review') || !own.length
        ? 'needs_review'
        : 'fact_clean';
    sentenceReviews.push({
      index,
      paragraph: sentence.paragraph,
      sentence: sentence.text,
      factIds,
      basis,
      findings: own,
      judgement,
    });
  });

  // ------------------------------------------------------------ mandatory
  const mandatory: MandatoryReview[] = [];
  for (const move of projection.moves) {
    mandatory.push({
      factId: move.id,
      summary: `${move.name} ${move.from ?? '?'} → ${move.to}`,
      expressed: expressedMoves.has(move.id),
      sentence: moveSentences.get(move.id) ?? null,
      form: 'literal',
    });
  }
  for (const task of projection.taskCompleted) {
    const sentence = sentenceReviews.find((entry) => entry.factIds.includes(task.id) && !entry.findings.some((f) => f.severity === 'fact'))?.sentence ?? null;
    mandatory.push({ factId: task.id, summary: `${task.name} 完成：${task.goal}`, expressed: taskLiteral.has(task.id), sentence, form: 'literal' });
  }
  for (const change of projection.sanityChanges) {
    const sentence = sentenceReviews.find((entry) => entry.factIds.includes(change.id))?.sentence ?? null;
    mandatory.push({
      factId: change.id,
      summary: `${change.name} 精神值 ${change.from} → ${change.to}`,
      expressed: sanityLiteral.has(change.id) || sanityReaction.has(change.id),
      sentence,
      form: sanityLiteral.has(change.id) ? 'literal' : sanityReaction.has(change.id) ? 'reaction' : 'missing',
    });
  }
  for (const change of projection.personalityAdded) {
    const sentence = sentenceReviews.find((entry) => entry.factIds.includes(change.id))?.sentence ?? null;
    mandatory.push({
      factId: change.id,
      summary: `${change.name} 新增个性：${change.text}`,
      expressed: personalityLiteral.has(change.id) || personalityReaction.has(change.id),
      sentence,
      form: personalityLiteral.has(change.id) ? 'literal' : personalityReaction.has(change.id) ? 'reaction' : 'missing',
    });
  }
  if (timeMinutes !== null) {
    mandatory.push({
      factId: 'time',
      summary: `时间推进 ${projection.timeText}`,
      expressed: timeExpressed,
      sentence: sentences.find((entry) => timeForms(entry.text).includes(timeMinutes))?.text ?? null,
      form: 'literal',
    });
  }

  // Prompt echo: the model copied the writing instructions into the prose.
  for (const marker of options.promptEchoMarkers ?? []) {
    if (marker && text.includes(marker)) {
      findings.push(finding(ctx, 'style.meta', sentences[0]?.text ?? text, 'the prose copies a writing instruction', [marker]));
      break;
    }
  }
  // Unlicensed entity: a known-but-not-licensed name used as if present.
  if (options.licensedEntities?.length) {
    const licensed = new Set(options.licensedEntities);
    for (const name of names) {
      if (licensed.has(name) || text.includes(name) === false) continue;
      findings.push(finding(ctx, 'fact.knowledge_leak', text.slice(0, 40),
        `${name} is not licensed for this point but is named in the prose`, [name]));
    }
  }
  if (options.maxChars !== undefined && charCount > options.maxChars) {
    findings.push(finding(ctx, 'style.truncated', last || text.slice(0, 40),
      `${charCount} > ${options.maxChars} characters`, []));
  }

  const counts = { fact: 0, style: 0, review: 0 };
  for (const entry of findings) counts[entry.severity] += 1;
  const blockingStyles = [...new Set(findings
    .filter((entry) => entry.severity === 'style' && BLOCKING_STYLE.has(entry.kind))
    .map((entry) => entry.kind))];
  const factLiterals = [
    ...projection.taskCompleted.map((entry) => entry.goal),
    ...projection.taskAdded.map((entry) => entry.goal),
    ...projection.personalityAdded.map((entry) => entry.text),
    ...projection.appearanceAdded.map((entry) => entry.text),
    ...projection.itemDescriptions,
    ...Object.values(projection.places).flatMap((place) => place.description),
    ...Object.values(projection.people).flatMap((person) => [...person.appearanceBefore, ...person.appearanceAfter]),
    ...(projection.timeText ? [projection.timeText] : []),
  ].filter((entry) => [...entry].length >= 8);
  const restatement = (sentence: SentenceReview): boolean => {
    if (sentence.findings.some((item) => SQUARE_FORM.has(item.kind))) return true;
    // A program fallback often prints "Name：…" lines and a "still there" line.
    if (/^[\p{Script=Han}]{2,4}：/u.test(sentence.sentence)) return true;
    if (/(?:还在|仍在|依旧在|留在原地)[^，。]{0,10}/u.test(sentence.sentence)) return true;
    for (const literal of factLiterals) {
      for (let index = 0; index + 8 <= literal.length; index += 4) {
        if (sentence.sentence.includes(literal.slice(index, index + 8))) return true;
      }
    }
    return false;
  };
  const factOnlySentences = sentenceReviews.filter(restatement).length;
  const ratio = dialogueRatio(text);
  const panelShare = sentences.length ? factOnlySentences / sentences.length : 0;
  const fallbackSuspicion = {
    suspected: sentences.length >= 2 && panelShare >= 0.6,
    factOnlySentences,
    sentences: sentences.length,
    dialogueRatio: ratio,
    panelShare,
    note: 'Most sentences restate settled fact text verbatim, which is what program fallbacks emit. Check the per-segment source before calling this model prose.',
  };
  return {
    id,
    chars: charCount,
    viewpoint: projection.viewpoint,
    time: {
      committed: projection.timeText,
      minutes: timeMinutes,
      expressed: timeExpressed,
      forms: [...new Set(forms)].sort((a, b) => a - b).map((value) => `${value}min`),
      repeated: timeMinutes === null ? 0 : forms.filter((value) => value === timeMinutes).length,
    },
    mandatory,
    sentences: sentenceReviews,
    findings,
    counts,
    metrics: {
      sentences: sentences.length,
      paragraphs: text.split(/\n\s*\n/u).filter((part) => part.trim()).length,
      dialogueRatio: dialogueRatio(text),
      boundSentences: sentenceReviews.filter((entry) => entry.factIds.length > 0).length,
      unboundSentences: sentenceReviews.filter((entry) => entry.judgement === 'needs_review').length,
      styleFindings: counts.style,
    },
    factsClean: counts.fact === 0,
    readable: blockingStyles.length === 0,
    blockingStyles,
    perspective: {
      viewpoint: projection.viewpoint,
      firstPerson: firstPersonSentence !== null,
      qualified: firstPersonSentence === null,
    },
    fallbackSuspicion,
    reviewer: 'ai-independent-checker-v1',
    disclaimer: 'Automated sentence-scoped review. `review` and `style` items are not passes; only a human reading decides quality. No human signature is implied.',
  };
}

/** True when a and b share a contiguous run of at least `size` characters. */
function sharesRun(a: string, b: string, size: number): boolean {
  for (let index = 0; index + size <= b.length; index += 1) {
    if (a.includes(b.slice(index, index + size))) return true;
  }
  return false;
}

const GOAL_COMPLETION = /(办完|做完|完成|搞定|达成|办妥|了结|终于|查到|查清|问清|找到|知道|确认|记下|对上|看完|翻完)/u;

/** Character bigrams of a goal, used to test whether the settled result is
 * present without the frozen wording. */
function goalTokens(goal: string): string[] {
  const cleaned = goal.replace(/[，。；：、「」（）()\s]/gu, '');
  const tokens: string[] = [];
  for (let index = 0; index + 2 <= cleaned.length; index += 1) tokens.push(cleaned.slice(index, index + 2));
  return [...new Set(tokens)];
}

function isAncestor(candidate: string, settled: string, projection: SceneProjection): boolean {
  let cursor = projection.places[settled]?.parent ?? null;
  let guard = 0;
  while (cursor && guard < 12) {
    if (cursor === candidate) return true;
    cursor = projection.places[cursor]?.parent ?? null;
    guard += 1;
  }
  return false;
}

function bareFieldSentence(narration: string, projection: SceneProjection): string | null {
  // Remove the actor, the frozen goal text, and completion/filler words; if
  // nothing with scene content remains, the sentence is a state field.
  const hasField = projection.taskCompleted.some((task) => narration.includes(task.goal))
    || projection.personalityAdded.some((change) => narration.includes(change.text))
    || /精神值|理智值|任务|个性|外貌/u.test(narration);
  if (!hasField) return null;
  let rest = narration;
  for (const name of projection.names) rest = rest.split(name).join('');
  for (const task of projection.taskCompleted) rest = rest.split(task.goal).join('');
  for (const change of projection.personalityAdded) rest = rest.split(change.text).join('');
  rest = rest.replace(/[「」“”"'，。；：、\s]/gu, '');
  rest = rest.replace(/把|这件事|这件|的事|事情|已经|终于|做完|办完|完成|搞定|达成|办妥|了结|了|的|也|还|就|都|又|再|后|以后/gu, '');
  if (rest.length > 6) return null;
  if (!projection.taskCompleted.length && !projection.personalityAdded.length) return null;
  return 'the sentence is only a settled field quoted back, with no scene content';
}

function boundFactIds(sentence: SentenceParts, projection: SceneProjection, names: readonly string[], ctx: ReviewContext): string[] {
  const ids: string[] = [];
  const narration = sentence.narration;
  for (const move of projection.moves) {
    if (mentions(narration, move.name, names) && narration.includes(move.to)) ids.push(move.id);
  }
  for (const change of projection.sanityChanges) {
    if (mentions(narration, change.name, names)) ids.push(change.id);
  }
  for (const task of projection.taskCompleted) {
    if (narration.includes(task.goal)) ids.push(task.id);
  }
  for (const change of projection.personalityAdded) {
    if (narration.includes(change.text)) ids.push(change.id);
  }
  for (const appearance of [...projection.appearanceAdded, ...projection.appearanceRemoved]) {
    if (narration.includes(appearance.text)) ids.push(appearance.id);
  }
  for (const [object, holder] of ctx.holders.holders) {
    if (narration.includes(object) && holder !== 'scene') ids.push(`item:${object}`);
  }
  for (const place of projection.visibleNames) {
    if (narration.includes(place)) ids.push(`place:${place}`);
  }
  return [...new Set(ids)];
}

function bigramCoverage(text: string, prior: string): number {
  const candidate = bigrams(normalize(text));
  if (!candidate.size) return 0;
  const previous = bigrams(normalize(prior));
  let shared = 0;
  for (const gram of candidate) if (previous.has(gram)) shared += 1;
  return shared / candidate.size;
}

function bigrams(text: string): Set<string> {
  const set = new Set<string>();
  for (let index = 0; index + 1 < text.length; index += 1) set.add(text.slice(index, index + 2));
  return set;
}

function dialogueRatio(text: string): number {
  const chars = [...text].length;
  if (!chars) return 0;
  let inside = 0;
  for (const match of text.matchAll(/「[^」]*」/gu)) inside += [...match[0]].length;
  return inside / chars;
}
