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
  INVENTABLE_OBJECTS, ITEM_HANDLING_VERBS, PAST_MARKERS, POSSESSION_VERBS, POSTURE, PROMISE_VERBS, SANITY_DOWN, SANITY_UP, SOFT_EVENT_VERBS,
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
        const direct = local.length === 1 && clause.trimEnd().endsWith(local[0].name)
          && clause.trimEnd().length - clause.indexOf(local[0].name) <= 2;
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
  /** Sentence index currently being reviewed. */
  index: number;
}

function finding(ctx: ReviewContext, kind: FindingKind, sentence: string, detail: string, basis: string[], factIds?: string[]): Finding {
  const severity = kind.startsWith('review.') ? 'review' : kind.startsWith('style.') ? 'style' : 'fact';
  return { kind, severity, sentence, detail, basis: basis.filter(Boolean), ...(factIds?.length ? { factIds } : {}) };
}

/** Is a verb licensed by the settled input or by a committed event? */
function verbLicensed(verb: string, ctx: ReviewContext, sentence: string): boolean {
  if (ctx.projection.sourceText.includes(verb)) return true;
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
  const ctx: ReviewContext = { projection, options, holders: buildHolders(projection), index: 0 };
  const sentenceReviews: SentenceReview[] = [];

  const charCount = [...text].length;
  const timeMinutes = projection.minutes;
  const forms = timeForms(text);
  const timeExpressed = timeMinutes !== null && forms.includes(timeMinutes);

  // ---------------------------------------------------------------- time
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
  for (const sentence of sentences) {
    for (const person of Object.values(projection.people)) {
      const settled = person.positionAfter ?? person.positionBefore;
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

  // ---------------------------------------------------------------- items
  const itemStateCovered = new Set<string>();
  for (const sentence of sentences) {
    const narration = sentence.narration;
    for (const [object, holder] of ctx.holders.holders) {
      const clause = possessionClause(narration, object);
      if (!clause) continue;
      const personHits = nameHits(clause, names, Object.keys(projection.people));
      const claimers = personHits.map((hit) => hit.name);
      const implied = projection.viewpoint && !claimers.length ? [projection.viewpoint] : claimers;
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
        findings.push(finding(ctx, 'fact.item_misattribution', sentence.text,
          `${object} is settled in the scene (${ctx.holders.basis.get(object)}) but is written as held`,
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
      const prop = [...ctx.holders.holders.keys()].find((entry) => possessionClause(narration, entry))
        ?? PROPS.find((entry) => possessionClause(narration, entry));
      if (!prop) continue;
      const verb = hasAny(possessionClause(narration, prop) ?? '', POSSESSION_VERBS);
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
      if (projection.sourceText.includes(verb)) {
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
      if (projection.sourceText.includes(verb)) continue;
      findings.push(finding(ctx, 'review.micro_action', sentence.text,
        `physical handling (${verb}) with no settled fact; allowed as a micro-action when it changes no settled state`, [], []));
    }
    for (const sound of SOUND_WORDS) {
      if (!narration.includes(sound)) continue;
      if (negatedAt(narration, sound)) continue;
      if (projection.sourceText.includes(sound)) continue;
      const moverHere = projection.moves.some((move) => move.kind === 'person' && narration.includes(move.name));
      if (sound === '脚步声' && moverHere) continue;
      findings.push(finding(ctx, 'fact.sound_added', sentence.text,
        `${sound} has no settled source`, [], []));
    }
    for (const marker of PAST_MARKERS) {
      if (!narration.includes(marker)) continue;
      if (projection.sourceText.includes(marker)) continue;
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
      if (projection.sourceText.includes(verb)) continue;
      if (negatedAt(narration, verb)) continue;
      findings.push(finding(ctx, 'fact.promise_added', sentence.text,
        `promise verb ${verb} has no settled basis`, [], []));
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
  for (const sentence of sentences) {
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
    if (/这一回合|本回合|回合结算|系统|状态已|按已结算/u.test(sentence.text)) {
      findings.push(finding(ctx, 'style.meta', sentence.text, 'meta/game-system wording inside prose', []));
    }
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
    ...(projection.timeText ? [projection.timeText] : []),
  ].filter((entry) => [...entry].length >= 8);
  const restatement = (sentence: SentenceReview): boolean => {
    if (sentence.findings.some((item) => SQUARE_FORM.has(item.kind))) return true;
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
