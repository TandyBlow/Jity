/** State-alignment grader for committed narration.
 *
 * The page currently accepts a model text only if every clause is one of two
 * exact templates per fact (`checkFactNarration`), so any real paraphrase falls
 * back to the template and the rendered narration is verbatim concatenation.
 * This grader replaces exact-clause matching with FACT ALIGNMENT:
 *
 * - a fact counts as expressed when ONE sentence binds its actor + payload;
 * - contradictions are hard violations (actor swap, reversed direction, wrong
 *   number, a completed task or a movement with no committed fact, an event
 *   verb with no committed fact);
 * - a sentence that binds nothing and contradicts nothing is UNVERIFIED, not
 *   fabricated. Out-of-vocabulary wording is an evidence flag for human
 *   review, never a fabrication verdict (design/narration-split-experiment-
 *   design.md §3: 词表外残差是「疑似错误提示」，不是捏造定罪).
 *
 * Deterministic, dependency-free, and sentence-scoped: a fact must be
 * asserted within one sentence, so cross-sentence token leakage cannot pass.
 * Time is graded only when the caller supplies it: §8.2 requires the passage
 * to be narrated, and an empty-delta point has nothing else to say. */
import type { TimeAdvance } from '../types';
import { factPhrases, type CommittedNarration, type NarrationFact } from './committed-narration';

export type ViolationKind =
  | 'actor_swap' | 'direction_reversed' | 'wrong_number'
  | 'task_claimed_without_fact' | 'movement_without_fact' | 'state_claim_without_fact'
  | 'wrong_time' | 'added_event' | 'empty_narration';

export interface AlignmentViolation { kind: ViolationKind; sentence: string; detail: string }
export interface FactCoverage { id: string; kind: NarrationFact['kind']; expressed: boolean }
export interface AlignmentResult {
  ok: boolean;
  /** 时间是否被述及（null = 调用方未提供 time）。 */
  timeRequired: boolean;
  coverage: FactCoverage[];
  omissions: string[];
  violations: AlignmentViolation[];
  /** 未绑定任何事实、也未构成矛盾的句子（软提示，不影响 ok）。 */
  unverified: string[];
  /** 与上一段文本的字符 bigram 最大重叠；无参照文本时为 null。 */
  repetition: number | null;
  timeExpressed: boolean | null;
}

const CN_DIGITS = ['零', '一', '二', '三', '四', '五', '六', '七', '八', '九'];
/** 1..99 的汉字读数（样本数值都在此范围；超出范围只认阿拉伯数字）。 */
export function cnNumber(value: number): string | null {
  if (!Number.isSafeInteger(value) || value < 0 || value > 99) return null;
  if (value < 10) return CN_DIGITS[value];
  const tens = Math.floor(value / 10), ones = value % 10;
  return `${tens === 1 ? '' : CN_DIGITS[tens]}十${ones === 0 ? '' : CN_DIGITS[ones]}`;
}

const escape = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/** Names inside 「」 are frozen task/personality text, not sentence actors:
 * "任务「帮主角熟悉校园」" names 主角 but the clause belongs to 学生B. */
const bareOf = (text: string) => text.replace(/「[^」]*」/g, '「」');

/** 2 is read 两 in front of a measure word; the other digits have one form. */
const CN_ALIASES: Record<number, string[]> = { 2: ['两'] };

/** A number is "mentioned" when it appears as an Arabic token or as its
 * Chinese reading. 12 must not be satisfied by 2 inside 12. */
export function mentionsNumber(sentence: string, value: number): boolean {
  const arabic = new RegExp(`(?<![0-9])${value}(?![0-9])`, 'u');
  if (arabic.test(sentence)) return true;
  const chinese = cnNumber(value);
  if (chinese !== null && sentence.includes(chinese)) return true;
  return (CN_ALIASES[value] ?? []).some((alias) => sentence.includes(alias));
}

const MOVE_VERB = '(?:走到|走向|来到|走进|进入|赶到|赶往|前往|抵达|走|跑|迈|移|去|到)';
/** 到达后的停留姿态：位置事实可以用「在/位于/站在…」表达（到达的结果），
 * 无事实背书的同类句式则落入站位违规检查。 */
const STANCE = '(?:在|位于|站在|待在|停在)';
const FROM_MARK = '(?:从|离开|自)';
const COMPLETION = /(完成|达成|做完|搞定|结束|成功|办完|了结)/;
const CHANGE_VERB = /(变|升|降|掉|减|增|恢复|回落|涨)/;

/** Event verbs that assert something HAPPENED. No committed fact kind is an
 * event, so one of these verbs is an added event wherever it stands — not
 * even the fact's own clause licenses it (三轮复核：推开门 不能由移动事实
 * 背书，重复主语也不能豁免). Quoted frozen text (「」) is not scanned. */
const EVENT_VERBS = ['推开', '踢开', '踹开', '冲进', '冲出', '奔跑', '跑向', '攻击', '开枪', '拔出', '举起',
  '捡起', '拾起', '递给', '塞进', '敲门', '打开', '关上', '锁上', '躲到', '藏在', '翻过', '爬上', '跳下',
  '喊住', '大叫', '大喊', '呼喊', '点燃', '砸碎', '撕开'];

function sentences(text: string): string[] {
  return text.split(/[。！？\n]+/).map((part) => part.trim()).filter(Boolean);
}

function hasArrival(sentence: string, from: string, to: string): boolean {
  const forward = new RegExp(`${FROM_MARK}[^。！？]{0,6}${escape(from)}[^。！？]{0,14}${MOVE_VERB}[^。！？]{0,6}${escape(to)}`);
  const reversed = new RegExp(`${FROM_MARK}[^。！？]{0,6}${escape(to)}[^。！？]{0,14}${MOVE_VERB}[^。！？]{0,6}${escape(from)}`);
  if (forward.test(sentence)) return true;
  if (reversed.test(sentence)) return false;
  // No explicit 从/离开: accept when both names occur in the from→to order and
  // a movement verb sits between them ("走廊这边走进大厅" is unusual, but the
  // tolerant order check keeps natural rewrites out of the omission bucket).
  const fromAt = sentence.indexOf(from), toAt = sentence.indexOf(to);
  if (fromAt >= 0 && toAt > fromAt) {
    const between = sentence.slice(fromAt + from.length, toAt);
    return new RegExp(MOVE_VERB).test(between);
  }
  return false;
}

function reversedArrival(sentence: string, from: string, to: string): boolean {
  return new RegExp(`${FROM_MARK}[^。！？]{0,6}${escape(to)}[^。！？]{0,14}${MOVE_VERB}[^。！？]{0,6}${escape(from)}`).test(sentence);
}

/** The clause that names the fact's actor, plus ONE following clause when a
 * movement spans a comma ("学生A离开走廊，走进大厅"). The walk stops at the
 * next roster name so a two-actor sentence cannot lend its second half to the
 * wrong fact. */
function scopeFor(fact: NarrationFact, sentence: string, names: Set<string>): string {
  const clauses = sentence.split(/[，,；;]/).filter(Boolean);
  const start = clauses.findIndex((part) => part.includes(fact.name));
  if (start < 0) return sentence;
  let scope = clauses[start];
  if (fact.kind === 'moved' && start + 1 < clauses.length) {
    const next = clauses[start + 1];
    if (![...names].some((name) => name !== fact.name && next.includes(name))) scope += `，${next}`;
  }
  return scope;
}

/** Degree adverbs may sit inside the frozen personality text (变得「十分」健谈
 * states the same change); anything else inserted between its words is a
 * different trait and must not bind (二轮复核：健壮而谈吐粗鲁 ≠ 健谈).
 * Negation is not handled anywhere in this grader (documented limit). */
const DEGREE_ADVERBS = '(?:十分|非常|特别|格外|相当|颇为|极为|极其|更加|越发|有些|很|挺)';
function loosePhrase(text: string): RegExp {
  return new RegExp(text.split('').map(escape).join(DEGREE_ADVERBS + '?'), 'u');
}

function binds(fact: NarrationFact, sentence: string, names: Set<string>): boolean {
  const named = sentence.includes(fact.name);
  // One clause is the base scope; up to two following clauses are joined as
  // long as no other roster character appears in them ("学生B完成了任务X。
  // 学生B变得健谈起来，精神值从10升到12。" needs the number clause too).
  const clauses = sentence.split(/[，,；;]/).filter(Boolean);
  const start = clauses.findIndex((part) => part.includes(fact.name));
  const scopes: string[] = [];
  if (start >= 0) {
    let scope = clauses[start];
    scopes.push(scope);
    for (let index = start + 1; index < clauses.length && index <= start + 2; index++) {
      if ([...names].some((name) => name !== fact.name && bareOf(clauses[index]).includes(name))) break;
      scope += `，${clauses[index]}`;
      scopes.push(scope);
    }
  } else scopes.push(sentence);
  const clause = scopeFor(fact, sentence, names);
  const matches = (scope: string): boolean => {
  switch (fact.kind) {
    case 'at': return named && scope.includes(fact.location);
    // Direction (from→to) when both endpoints are stated; a destination-only
    // clause still expresses the move — as a movement verb («走向大厅») or as
    // the stance at the destination («在大厅»), the committed delta's only
    // free parameter is the endpoint, and the origin must stay unclaimed.
    case 'moved': return named && (hasArrival(scope, fact.from, fact.to)
      || (!scope.includes(fact.from) && scope.includes(fact.to)
        && (new RegExp(MOVE_VERB).test(scope) || new RegExp(STANCE).test(scope))));
    case 'sanity': return named && mentionsNumber(scope, fact.value);
    case 'sanity_changed': return named && CHANGE_VERB.test(scope)
      && (mentionsNumber(scope, fact.from) || mentionsNumber(scope, fact.to));
    case 'task_achieved': return named && scope.includes(fact.goal) && COMPLETION.test(scope);
    case 'personality_changed': return named && (scope.includes(fact.text) || loosePhrase(fact.text).test(scope));
  }
  return false;
  };
  if (scopes.some(matches)) return true;
  // Movement may still be asserted across the very next comma without a name.
  return fact.kind === 'moved' && named && (hasArrival(clause, fact.from, fact.to)
    || (!clause.includes(fact.from) && clause.includes(fact.to)
      && (new RegExp(MOVE_VERB).test(clause) || new RegExp(STANCE).test(clause))));
}

/** Content signature: does the sentence talk ABOUT this fact (regardless of
 * whether the actor is right)? Used to catch actor swaps, where the payload
 * is correct but attached to the wrong character. */
function signature(fact: NarrationFact, sentence: string): boolean {
  switch (fact.kind) {
    // Strong signatures only: a weak one (a bare destination, a shared sanity
    // value) would flag a correct sentence about a DIFFERENT actor as a swap.
    case 'at': return sentence.includes(fact.location) && !new RegExp(MOVE_VERB).test(sentence);
    case 'moved': return hasArrival(sentence, fact.from, fact.to);
    case 'sanity': return mentionsNumber(sentence, fact.value);
    case 'sanity_changed': return mentionsNumber(sentence, fact.from) && mentionsNumber(sentence, fact.to);
    case 'task_achieved': return sentence.includes(fact.goal);
    case 'personality_changed': return sentence.includes(fact.text);
  }
}

// minute 不收裸「分」：十分健谈的「分」是程度副词，不是分钟（2026-10-28 复核）。
const UNIT_WORDS: Record<TimeAdvance['duration']['unit'], string[]> = {
  second: ['秒', '秒后'], minute: ['分钟'], hour: ['小时', '个钟头'], day: ['天', '日'],
  month: ['个月', '月'], year: ['年'],
};

/** Ordinal counters before a unit word («第二天», «第3分钟») name a POSITION in
 * time, not an elapsed duration; they are masked out before matching. */
const ordinalSpan = (words: string[]): RegExp =>
  new RegExp(`第\\s*[0-9零一二两三四五六七八九十百]{1,3}\\s*(?:个)?\\s*(?:${words.map(escape).join('|')})`, 'gu');

/** Every duration actually written for this unit, Arabic or Chinese, adjacent
 * to the unit word up to whitespace ("两分钟", "2 分钟", "30秒"). A bare
 * Chinese digit as a substring is NOT a duration: 四 in 四周 is not four
 * minutes; 二 in 第二天 is an ordinal day, not two days. */
export function durationsIn(sentence: string, unit: TimeAdvance['duration']['unit']): number[] {
  const words = UNIT_WORDS[unit];
  const scanned = sentence.replace(ordinalSpan(words), '§');
  const found = new Set<number>();
  for (const word of words) {
    for (const match of scanned.matchAll(new RegExp(`([0-9]+)\\s*(?:个)?\\s*${escape(word)}`, 'gu'))) {
      found.add(Number(match[1]));
    }
    for (let value = 1; value <= 99; value++) {
      const reading = cnNumber(value);
      if (reading && new RegExp(`${reading}\\s*(?:个)?\\s*${escape(word)}`, 'u').test(scanned)) found.add(value);
      for (const alias of CN_ALIASES[value] ?? []) {
        if (new RegExp(`${alias}\\s*(?:个)?\\s*${escape(word)}`, 'u').test(scanned)) found.add(value);
      }
    }
  }
  return [...found];
}

/** Time mention: a duration adjacent to the unit word. "过了一会儿" does not
 * satisfy a 2-minute advance, and a wrong duration is a fact error. */
export function mentionsTime(sentence: string, time: { amount: number; unit: TimeAdvance['duration']['unit'] }): boolean {
  return durationsIn(sentence, time.unit).includes(time.amount);
}

const ALL_UNIT_WORDS = [...new Set(Object.values(UNIT_WORDS).flat())];
const ANY_ORDINAL_SPAN = ordinalSpan(ALL_UNIT_WORDS);
const ANY_DURATION_SPAN =
  new RegExp(`(?:[0-9]+|[零一二两三四五六七八九十]{1,3})\\s*(?:个)?\\s*(?:${ALL_UNIT_WORDS.map(escape).join('|')})`, 'gu');

/** Every value a sentence states: Arabic tokens, plus Chinese readings 1..99
 * WHEN they sit in a value position (直接跟在 从/到/为/是/至 之后——「值」不算，
 * 否则 精神值一路 的「一」会被当成数值 1). Ordinal counters and durations are
 * masked first, so «第三个» and «两分钟» never enter the check; idiomatic
 * numerals outside value positions (三心二意) are not extracted at all. This
 * is what makes 从十升到十三 a wrong_number. */
export function numbersIn(sentence: string): number[] {
  const masked = sentence.replace(ANY_ORDINAL_SPAN, '§').replace(ANY_DURATION_SPAN, '§');
  const found = new Set<number>();
  for (const match of masked.matchAll(/(?<![0-9])([0-9]+)(?![0-9])/gu)) found.add(Number(match[1]));
  for (let value = 1; value <= 99; value++) {
    const reading = cnNumber(value);
    if (!reading) continue;
    if (new RegExp(`(?<=[从到为是至])${reading}(?![0-9零一二两三四五六七八九十])`, 'u').test(masked)) found.add(value);
    for (const alias of CN_ALIASES[value] ?? []) {
      if (new RegExp(`(?<=[从到为是至])${alias}(?![0-9零一二两三四五六七八九十])`, 'u').test(masked)) found.add(value);
    }
  }
  return [...found];
}

function bigrams(text: string): Set<string> {
  const stripped = text.replace(/[\s，。！？；：、「」]/g, '');
  const out = new Set<string>();
  for (let index = 0; index + 1 < stripped.length; index++) out.add(stripped.slice(index, index + 2));
  return out;
}

export function repetitionAgainst(text: string, previous: string | null | undefined): number | null {
  if (!previous) return null;
  const a = bigrams(text), b = bigrams(previous);
  if (!a.size || !b.size) return null;
  let shared = 0;
  for (const gram of a) if (b.has(gram)) shared += 1;
  return shared / Math.max(a.size, b.size);
}

export interface AlignmentOptions {
  time?: { amount: number; unit: TimeAdvance['duration']['unit'] } | null;
  previousText?: string | null;
  /** Roster of display names; defaults to the names carried by the facts. */
  roster?: string[];
  /** Locations that exist in the world. A refused action has no fact at all,
   * so without this list a claimed movement to a known place would slip
   * through as an unverified sentence instead of a contradiction. */
  locations?: string[];
  /** 是否把「未述时间」算作失败。默认 false：现有 renderCommittedNarration
   * 根本不写时间，把它并进事实错误会掩盖「模板缺时间」这个独立发现。
   * 三个臂都按同一口径判事实，时间覆盖由 harness 单独统计。 */
  requireTime?: boolean;
}

export function alignNarration(packet: CommittedNarration, text: string, options: AlignmentOptions = {}): AlignmentResult {
  const requireTime = options.requireTime === true;
  const parts = sentences(text);
  const names = new Set(options.roster ?? packet.facts.map((fact) => fact.name));
  const violations: AlignmentViolation[] = [];
  const unverified: string[] = [];
  const coverage = new Map<string, boolean>(packet.facts.map((fact) => [fact.id, false]));
  let timeExpressed: boolean | null = options.time ? false : null;
  if (!parts.length) {
    violations.push({ kind: 'empty_narration', sentence: '', detail: 'empty or whitespace-only narration' });
  }
  for (const sentence of parts) {
    if (timeExpressed === false && options.time && mentionsTime(sentence, options.time)) timeExpressed = true;
    const bound = packet.facts.filter((fact) => binds(fact, sentence, names));
    // A sentence may express more than one fact (a natural sentence often
    // joins a task with its personality/sanity consequence); every bound fact
    // counts, but only once per fact overall.
    for (const fact of bound) coverage.set(fact.id, true);

    // 1. Wrong duration. ANY time unit in the sentence is checked, not only
    // the expected one: a 2-second point narrated as "两分钟" states the wrong
    // unit, which is just as wrong as the wrong amount.
    if (options.time) {
      const declared = Object.keys(UNIT_WORDS).flatMap((unit) =>
        durationsIn(sentence, unit as TimeAdvance['duration']['unit'])
          .map((amount) => ({ unit: unit as TimeAdvance['duration']['unit'], amount })));
      const wrong = declared.find((entry) => entry.unit !== options.time!.unit || entry.amount !== options.time!.amount);
      if (wrong) {
        violations.push({ kind: 'wrong_time', sentence,
          detail: `${wrong.amount} ${wrong.unit} vs expected ${options.time.amount} ${options.time.unit}` });
        continue;
      }
    }

    // 2. Actor swap: the payload belongs to a fact whose actor is NOT named,
    // while a different roster character IS named in the payload clause.
    // Weak signatures (a bare destination shared by several actors) only
    // checked while the fact is UNBOUND — a bound at-fact makes same-payload
    // clauses about other actors benign («学生A已经在大厅里等着了» next to
    // 主角's at-fact). Strong signatures stay checked even when bound: a
    // clause re-attaching 12→9 to 学生D is a swap, not a restatement
    // (复核重跑 hv-sanity-1 首稿原样).
    const clauses = sentence.split(/[，,；;]/).filter(Boolean);
    const WEAK_SIGNATURE = new Set<NarrationFact['kind']>(['at']);
    let swappedOut = false;
    for (const fact of packet.facts) {
      if (bound.includes(fact) && WEAK_SIGNATURE.has(fact.kind)) continue;
      const swapped = clauses.find((clause) => signature(fact, clause)
        && [...names].some((name) => bareOf(clause).includes(name) && name !== fact.name));
      if (swapped) {
        const attributed = [...names].filter((name) => bareOf(swapped).includes(name)).join('/');
        violations.push({ kind: 'actor_swap', sentence,
          detail: `payload of ${fact.id} attributed to ${attributed} instead of ${fact.name}` });
        swappedOut = true;
        break;
      }
    }
    if (swappedOut) continue;

    // 3. Direction reversal, per clause: one sentence may carry two opposite
    // moves, and each actor's clause is what the reader binds.
    let reversedOut = false;
    for (const fact of packet.facts) {
      if (fact.kind !== 'moved' || !sentence.includes(fact.name)) continue;
      const clause = sentence.split(/[，,；;]/).find((part) => part.includes(fact.name)) ?? sentence;
      if (reversedArrival(clause, fact.from, fact.to)) {
        violations.push({ kind: 'direction_reversed', sentence, detail: `${fact.name}: ${fact.to} -> ${fact.from}` });
        reversedOut = true;
        break;
      }
    }
    if (reversedOut) continue;

    // 3.5 A movement asserted for an actor whose committed position is 'at':
    // the delta says this actor did not move, so the arrival is invented
    // («主角从走廊来到大厅时…» on a point where only 学生A moved — the same
    // sentence the destination-stance binding above makes legitimate for the
    // actor that DID move).
    let fabricatedOut = false;
    for (const fact of packet.facts) {
      if (fact.kind !== 'at' || !sentence.includes(fact.name)) continue;
      const clause = sentence.split(/[，,；;]/).find((part) => part.includes(fact.name)) ?? sentence;
      if (new RegExp(`${FROM_MARK}[^，。！？]{0,8}${MOVE_VERB}`).test(clause)) {
        violations.push({ kind: 'movement_without_fact', sentence,
          detail: `${fact.name} is committed at ${fact.location} with no movement this point` });
        fabricatedOut = true;
        break;
      }
    }
    if (fabricatedOut) continue;

    // 4. Numeric errors on a named sanity fact.
    let numberOut = false;
    for (const fact of packet.facts) {
      if (fact.kind !== 'sanity' && fact.kind !== 'sanity_changed') continue;
      if (!sentence.includes(fact.name)) continue;
      if (fact.kind === 'sanity_changed' && !CHANGE_VERB.test(sentence)) continue;
      const allowed = fact.kind === 'sanity' ? [fact.value] : [fact.from, fact.to];
      const numbers = numbersIn(sentence);
      const wrong = numbers.find((value) => !allowed.includes(value));
      if (wrong !== undefined) {
        violations.push({ kind: 'wrong_number', sentence, detail: `${fact.name}: ${wrong} not in [${allowed.join(', ')}]` });
        numberOut = true;
        break;
      }
    }
    if (numberOut) continue;

    const locations = [...new Set([...(options.locations ?? []),
      ...packet.facts.flatMap((fact) => fact.kind === 'at' ? [fact.location] : fact.kind === 'moved' ? [fact.from, fact.to] : [])])];

    // 5. Standing-location claim with no committed position fact ("学生A位于
    // 走廊" when the point only places 学生B in the hall). Checked even when
    // another fact in the same sentence is correctly bound.
    const positions = packet.facts.filter((fact): fact is Extract<NarrationFact, { kind: 'at' | 'moved' }> =>
      fact.kind === 'at' || fact.kind === 'moved');
    // 零位置事实的点（拒绝行动/空增量）同样受检：positions 为空时任何站位
    // 声明都无事实背书——2026-10-28 复核前这里的 positions.length > 0 短路
    // 让三个空点上的任意站位都被放行。
    const stateClaim = [...names].flatMap((name) => locations
      .filter((location) => new RegExp(`${escape(name)}[^。！？]{0,8}${STANCE}[^。！？]{0,4}${escape(location)}`).test(sentence))
      .map((location) => ({ name, location })))
      .find((claim) => !positions.some((fact) => fact.name === claim.name
        && (fact.kind === 'at' ? fact.location === claim.location
          : fact.to === claim.location || fact.from === claim.location)));
    if (stateClaim) {
      violations.push({ kind: 'state_claim_without_fact', sentence,
        detail: `${stateClaim.name} at ${stateClaim.location} has no committed position fact` });
      continue;
    }

    // 5.5 A completion claim riding on a bound non-task fact («学生A在大厅内
    // 完成任务» beside a bound position fact): the bound-fact gate below would
    // wave it through, so completion+任务 wording naming a roster actor is
    // checked here even when the sentence binds something else. Recap clauses
    // that name no actor («整个任务顺利结束了») stay out of scope.
    if (COMPLETION.test(sentence) && /任务|「|」/.test(sentence)
      && !packet.facts.some((fact) => fact.kind === 'task_achieved' && bound.includes(fact))) {
      const completionClause = clauses.find((part) => COMPLETION.test(part)
        && [...names].some((name) => bareOf(part).includes(name)));
      if (completionClause) {
        violations.push({ kind: 'task_claimed_without_fact', sentence,
          detail: 'completion claim names an actor but no task_achieved fact binds this sentence' });
        continue;
      }
    }

    // 5.6 An event verb anywhere is an added event, bound fact or not: the
    // previous bound-gate exemption let both a repeated-subject clause
    // («学生A打开门» — the actor's name was read as backing) and the fact's
    // own clause («推开门») escape, though no committed fact kind licenses an
    // event. Quoted frozen text does not count (目标原文自带动词的引用).
    const event = EVENT_VERBS.find((verb) => bareOf(sentence).includes(verb));
    if (event) {
      violations.push({ kind: 'added_event', sentence, detail: `event verb ${event} has no committed fact` });
      continue;
    }

    if (bound.length) continue;

    // 6. Task completion claimed with no committed task fact.
    if (COMPLETION.test(sentence) && /任务|「|」/.test(sentence)) {
      violations.push({ kind: 'task_claimed_without_fact', sentence, detail: 'no task_achieved fact matches this completion' });
      continue;
    }

    // 7. Movement claimed to a known location with no committed position fact.
    // Mask the location names first: 「走廊」 itself contains 走, so testing the
    // verb on the raw sentence would turn every mention of it into a claim.
    const masked = locations.reduce((text, location) => text.split(location).join('§'), sentence);
    const adjacent = new RegExp(`(?:${MOVE_VERB})[^，。！？]{0,4}§|§[^，。！？]{0,4}(?:${MOVE_VERB})`);
    const moveClaim = locations.find((location) => sentence.includes(location) && adjacent.test(masked));
    if (moveClaim) {
      violations.push({ kind: 'movement_without_fact', sentence, detail: `claims movement involving ${moveClaim}` });
      continue;
    }

    if (options.time && mentionsTime(sentence, options.time)) continue; // accounted by timeExpressed
    unverified.push(sentence);
  }
  const omissions = packet.facts.filter((fact) => !coverage.get(fact.id)).map((fact) => {
    // The template phrase is the human-readable name of the missing fact.
    return factPhrases(fact)[0];
  });
  const repetition = repetitionAgainst(text, options.previousText);
  return {
    ok: violations.length === 0 && omissions.length === 0 && !(requireTime && timeExpressed === false),
    timeRequired: requireTime,
    coverage: packet.facts.map((fact) => ({ id: fact.id, kind: fact.kind, expressed: coverage.get(fact.id) === true })),
    omissions, violations, unverified, repetition, timeExpressed,
  };
}
