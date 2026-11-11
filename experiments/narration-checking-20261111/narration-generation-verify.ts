/** Faithfulness gate for the constrained route.
 *
 * Two layers:
 *  1. the existing `alignNarration` grader for the base facts (movement
 *     direction, actor binding, task/personality, added events, numbers, time);
 *  2. this route's own binding for the facts the base grader has no vocabulary
 *     for (appearance text, subtask, sanity direction, item presence) plus
 *     licensing: no unregistered name, no unlicensed number, no rediscovery
 *     claim, no prompt echo.
 *
 * A rejected text is evidence, not a fallback: `generateCandidate` repairs at
 * beat level and re-verifies.
 */
import type { EntityDelta, Id, TimeAdvance } from '../../../types';
import { resultSemantics, settledViolationsFromScene } from '../../narration-generation/licensed-sense';

/** Character-bigram recall of `expected` inside `text`, ignoring punctuation and
 * whitespace. Used only for free-text results, which have no structured fields:
 * it answers «is this sentence's content actually in the prose», not «is the
 * wording identical». */
export function contentRecall(text: string, expected: string): number {
  const clean = (value: string) => value.replace(/[\s，。；：！？、「」『』…—\-·“”"'（）()]/gu, '');
  const target = clean(expected);
  const source = clean(text);
  if (!target) return 1;
  if (target.length < 2) return source.includes(target) ? 1 : 0;
  const grams: string[] = [];
  for (let i = 0; i + 1 < target.length; i += 1) grams.push(target.slice(i, i + 2));
  const hit = grams.filter((gram) => source.includes(gram)).length;
  return hit / grams.length;
}
import { alignNarration, mentionsTime, numbersIn, repetitionAgainst } from '../../../runtime/narration-alignment';
import type { CommittedNarration } from '../../../runtime/committed-narration';
import type { CandidateIssue, FactVisibility, SceneFact, SceneSkeleton } from './types';

export interface VerifyOptions {
  scene: SceneSkeleton;
  base: CommittedNarration;
  priorText?: string | null;
  /** Restrict coverage to these fact ids (beat verification). */
  factIds?: string[];
  /** Skip length rules (beat verification). */
  minChars?: number;
  maxChars?: number;
  /** Deprecated compatibility field; omission of elapsed time is allowed. */
  requireTime?: boolean;
  sanityStyle?: 'direction' | 'number';
  forbiddenKnowledge?: string[];
  /** Check repetition against prior text (final verification only). */
  checkPrior?: boolean;
}

import { SANITY_DOWN_CUES as DOWN_CUES, SANITY_UP_CUES as UP_CUES } from './realize';
const REDISCOVERY = /(第一次|头一次|头一回|第一次看见|这才注意到|第一次注意)/;
const PRIVATE_THOUGHT = /(心想|心里想|暗自想|在心里想|心中想|暗自盘算)/;
const PROMPT_ECHO = /(必须全部|输出格式|只输出正文|【正文】|JSON)/;
// A bullet list or a "fact:" line is the model handing back the brief instead
// of writing prose — the exact regression this route was built to stop.
const NEWLINES = new RegExp(String.fromCharCode(10) + '+', 'u');
const FACT_LIST_LINE = /^\s*(?:[-*•]|\d+[.、)])\s*/u;
const FACT_LABEL = /^\s*(?:事实|时间|地点|人物|变化|任务|结果|场景)[:：]/u;
const EVENT_VERBS = ['推开', '踢开', '踹开', '冲进', '冲出', '奔跑', '跑向', '攻击', '开枪', '拔出', '举起',
  '捡起', '拾起', '递给', '塞进', '敲门', '打开', '关上', '锁上', '躲到', '藏在', '翻过', '爬上', '跳下',
  '喊住', '大叫', '大喊', '呼喊', '点燃', '砸碎', '撕开', '拿出', '掏出'];

function sentences(text: string): string[] {
  return text.split(/[。！？\n]+/u).map((part) => part.trim()).filter(Boolean);
}

function stripEnd(text: string): string {
  return text.replace(/[。！？!?；;，,、\s]+$/u, '').trim();
}

function maskLicensed(text: string, licensed: string[]): string {
  let masked = text;
  for (const span of licensed) {
    if (!span || span.length < 4) continue;
    for (const variant of [span, stripEnd(span)]) {
      if (variant.length >= 4) masked = masked.split(variant).join('＿'.repeat([...variant].length));
    }
  }
  return masked;
}

function licenseMask(text: string, licensed: string[]): boolean[] {
  const mask = new Array<boolean>(text.length).fill(false);
  for (const name of licensed) {
    if (!name) continue;
    let from = 0;
    while (from <= text.length) {
      const at = text.indexOf(name, from);
      if (at < 0) break;
      for (let index = at; index < at + name.length; index += 1) mask[index] = true;
      from = at + 1;
    }
  }
  return mask;
}

/** A name is tolerated only when every occurrence sits inside a licensed name. */
function unlicensedName(text: string, name: string, mask: boolean[]): string | null {
  if (!name || name.length < 1) return null;
  let from = 0;
  while (from <= text.length) {
    const at = text.indexOf(name, from);
    if (at < 0) return null;
    if (!mask[at] || !mask[at + name.length - 1]) return name;
    from = at + 1;
  }
  return null;
}

function bindWithName(text: string, name: string, needle: string): boolean {
  const parts = text.split(/(?<=[。！？])/u).map((part) => part.trim()).filter(Boolean);
  for (let index = 0; index < parts.length; index += 1) {
    if (!parts[index].includes(needle)) continue;
    if (parts[index].includes(name)) return true;
    if (index > 0 && parts[index - 1].includes(name)) return true;
  }
  return false;
}

function cuePresent(sentence: string, cues: string[]): boolean {
  return cues.some((cue) => sentence.includes(cue));
}

export function verifyText(text: string, options: VerifyOptions): {
  ok: boolean;
  coverage: { factId: string; kind: SceneFact['kind']; expressed: boolean; mandatory: boolean }[];
  issues: CandidateIssue[];
  unverifiedSentences: string[];
  chars: number;
  repetition: number | null;
} {
  const { scene } = options;
  const issues: CandidateIssue[] = [];
  const inScope = (fact: SceneFact): boolean => !options.factIds || options.factIds.includes(fact.id);
  const facts = scene.facts.filter((fact) => inScope(fact) && fact.visibility === 'scene');
  const roster = new Set([...scene.licensed.names, ...scene.worldNames.characters]);
  const parts = sentences(text);
  const chars = [...text].length;
  // Elapsed time constrains chronology, not the prose's inventory. Keep wrong
  // durations checked by alignNarration, but never require an elapsed-time line,
  // including when an older caller still passes requireTime: true.
  const requireTime = false;
  const sanityStyle = options.sanityStyle ?? 'direction';

  if (!parts.length) {
    issues.push({ kind: 'empty_text', severity: 'hard', beatId: null, detail: 'empty narration' });
  }

  // ---- 1. base grader -------------------------------------------------------
  const base: CommittedNarration = options.base;
  const alignment = alignNarration(base, text, {
    time: scene.time ? { amount: scene.time.duration.amount, unit: scene.time.duration.unit } : null,
    requireTime,
    roster: scene.worldNames.characters,
    locations: [...new Set([...scene.worldNames.locations, ...scene.licensed.locations])],
    knownPositions: scene.facts
      .filter((fact): fact is Extract<SceneFact, { kind: 'at' }> => fact.kind === 'at')
      .map((fact) => ({ name: fact.name, location: fact.location })),
  });
  // A beat may not repeat a sentence the player read last turn verbatim. The
  // writer is free to rephrase; the program realizer already rotates variants.
  if (options.priorText) {
    const previous = new Set(sentences(options.priorText).map((part) => stripEnd(part)));
    for (const part of parts) {
      const core = stripEnd(part);
      if (core && previous.has(core)) {
        issues.push({ kind: 'echo_prior', severity: 'hard', beatId: null, detail: `repeats last turn: ${core}`, sentence: part });
        break;
      }
    }
    // A model can avoid verbatim repetition while still reusing the same
    // opening frame every turn. That is a soft issue: it asks for one rewrite
    // with an explicit instruction, but it does not by itself reject the turn.
    const priorOpenings = sentences(options.priorText)
      .map((part) => [...stripEnd(part)].slice(0, 6).join(''))
      .filter((part) => [...part].length >= 6);
    const first = [...stripEnd(parts[0] ?? '')].slice(0, 6).join('');
    if (first.length >= 6 && priorOpenings.includes(first)) {
      issues.push({ kind: 'opening_repeat', severity: 'soft', beatId: null, detail: `same opening as last turn: ${first}`, sentence: parts[0] });
    }
  }

  for (const violation of alignment.violations) {
    // Two actors moving along the same route share one payload signature; the
    // legacy grader then attributes the other actor's move to the named one.
    // If the named actor has an identical committed move, this is not a swap.
    if (violation.kind === 'actor_swap') {
      const id = /^payload of (\S+) attributed to/u.exec(violation.detail)?.[1];
      const fact = id ? base.facts.find((entry) => entry.id === id) : undefined;
      if (fact) {
        // Two actors moving along the same route share one payload signature;
        // the legacy grader then attributes the other actor's move to the
        // named one. If the named actor has an identical committed move, this
        // is not a swap.
        if (fact.kind === 'moved' && base.facts.some((other) => other.kind === 'moved'
          && other.id !== fact.id && other.from === fact.from && other.to === fact.to
          && violation.sentence.includes(other.name))) {
          continue;
        }
        const others = [...roster].filter((name) => name !== fact.name && violation.sentence.includes(name));
        // A name that only occurs inside the fact's own name ("路明非的护目镜"
        // contains 路明非) is not a second actor.
        if (others.length && others.every((name) => fact.name.includes(name))) continue;
        // A bystander's presence sentence ("唐骁也在中央庭院") shares the
        // location payload of the viewpoint's at-fact. When that bystander has
        // their own committed position for the same place, it is presence.
        if (fact.kind === 'at' || fact.kind === 'moved') {
          const target = fact.kind === 'at' ? fact.location : fact.to;
          const licensedThere = others.some((name) => scene.facts.some((entry) => {
            if (entry.visibility !== 'scene' || entry.kind === 'time') return false;
            if (!('name' in entry) || entry.name !== name) return false;
            return entry.kind === 'at' ? entry.location === target : entry.kind === 'move' ? entry.to === target : false;
          }));
          if (licensedThere) continue;
        }
      }
    }
    // An event verb that only survives inside a settled description (a room
    // appearance that says the lock was opened) is quoted state, not an
    // invented event: drop it from the gate's event check.
    if (violation.kind === 'added_event') {
      const remainder = maskLicensed(violation.sentence, [...scene.licensed.details, ...scene.licensed.quotes]);
      if (!EVENT_VERBS.some((verb) => remainder.includes(verb))) continue;
    }
    const kind: CandidateIssue['kind'] = violation.kind === 'direction_reversed' ? 'fact_direction_reversed'
      : violation.kind === 'actor_swap' ? 'fact_actor_swap'
        : violation.kind === 'wrong_number' ? 'fact_wrong_number'
          : violation.kind === 'wrong_time' ? 'fact_time_wrong'
            : violation.kind === 'task_claimed_without_fact' ? 'task_without_fact'
              : violation.kind === 'movement_without_fact' ? 'movement_without_fact'
                : violation.kind === 'added_event' ? 'unlicensed_event'
                  : violation.kind === 'empty_narration' ? 'empty_text'
                    : 'unlicensed_event';
    issues.push({ kind, severity: 'hard', beatId: null, detail: violation.detail, sentence: violation.sentence });
  }

  // ---- 2. route-specific fact binding --------------------------------------
  const coverage: { factId: string; kind: SceneFact['kind']; expressed: boolean; mandatory: boolean }[] = [];
  const baseCoverage = new Map(alignment.coverage.map((entry) => [entry.id, entry.expressed]));
  const presentNames = new Set(scene.present.map((person) => person.name));
  for (const fact of facts) {
    let expressed = false;
    if (fact.kind === 'time') {
      expressed = mentionsTime(text, { amount: fact.advance.duration.amount, unit: fact.advance.duration.unit });
    } else if (fact.kind === 'move' || fact.kind === 'task_achieved' || fact.kind === 'personality_changed') {
      expressed = baseCoverage.get(fact.id) === true;
    } else if (fact.kind === 'appearance_changed') {
      const needle = fact.removed ? fact.supersededTexts[0] ?? '' : fact.text ?? '';
      // A room's new look does not need its own name in the sentence; the
      // settled text is unique and already licensed.
      expressed = Boolean(needle) && (fact.entityKind === 'location'
        ? text.includes(stripEnd(needle))
        : bindWithName(text, fact.name, stripEnd(needle)));
    } else if (fact.kind === 'subtask_added') {
      expressed = bindWithName(text, fact.name, stripEnd(fact.goal));
    } else if (fact.kind === 'sanity_changed') {
      if (sanityStyle === 'number') {
        expressed = parts.some((sentence) => sentence.includes(fact.name)
          && (numbersIn(sentence).includes(fact.from) || numbersIn(sentence).includes(fact.to))
          && /(变|升|降|落|回)/u.test(sentence));
      } else {
        const direction = fact.to < fact.from ? 'down' : fact.to > fact.from ? 'up' : 'flat';
        const cues = direction === 'down' ? DOWN_CUES : direction === 'up' ? UP_CUES : ['没有变', '照旧'];
        expressed = parts.some((sentence) => sentence.includes(fact.name) && cuePresent(sentence, cues));
      }
    } else if (fact.kind === 'item_present' || fact.kind === 'item_discovered') {
      expressed = parts.some((sentence) => sentence.includes(fact.name));
    } else if (fact.kind === 'result') {
      if (fact.structured) {
        // Structured record: compare meaning, not wording. Actor, target and
        // outcome direction must agree; a faithful paraphrase is accepted and
        // a dropped negation / swapped actor / reversed outcome is not.
        const check = resultSemantics(text, fact.text, {
          actor: fact.structured.actor,
          action: fact.structured.action,
          target: fact.structured.target,
          outcome: fact.structured.outcome,
        }, [fact.structured.actor, fact.structured.target].filter(Boolean) as string[]);
        expressed = check.ok;
        if (!check.ok) {
          issues.push({
            kind: 'result_semantics', severity: 'hard', beatId: null,
            detail: `result:${fact.id}:${check.detail}${check.sentence ? ` | ${check.sentence}` : ''}`,
          });
        } else if (check.unverified) {
          // A record with no decidable direction cannot be automatically passed:
          // keep it visible for manual reading instead of calling it verified.
          issues.push({ kind: 'result_unverified', severity: 'soft', beatId: null, detail: `result:${fact.id}:${check.detail}` });
        }
      } else {
        // Free-text only (no 04 record). The wording is a rendering, not a
        // contract, but there are no fields to compare either — so require the
        // fact's own content to be largely present (character-bigram recall)
        // rather than an exact sentence, and always mark it unverified: only a
        // human read can confirm a free-text outcome.
        const coverage = contentRecall(text, fact.text);
        expressed = coverage >= 0.55;
        if (!expressed) {
          issues.push({
            kind: 'fact_missing', severity: 'hard', beatId: null,
            detail: `result:${fact.id}:「${fact.text}」(content recall ${coverage.toFixed(2)})`,
          });
        } else {
          issues.push({
            kind: 'result_unverified', severity: 'soft', beatId: null,
            detail: `result:${fact.id}: free-text result covered by ${(coverage * 100).toFixed(0)}% content; not machine-verified`,
          });
        }
      }
    } else if (fact.kind === 'at') {
      expressed = parts.some((sentence) => sentence.includes(fact.name) && sentence.includes(fact.location));
    }
    const mandatory = fact.kind !== 'time' && fact.mandatory;
    coverage.push({ factId: fact.id, kind: fact.kind, expressed, mandatory });
    if (mandatory && !expressed) {
      issues.push({
        kind: 'fact_missing', severity: 'hard', beatId: null,
        // The retry has to know what was required; «result:facts:result» alone
        // cannot be acted on. The settled sentence is short and already licensed.
        detail: fact.kind === 'result' ? `result:${fact.id}:「${fact.text}」` : `${fact.kind}:${fact.id}`,
      });
    }
  }

  // ---- 2.5 settled scene states (02's checks) -------------------------------
  // The constrained route had its own licensing but none of 02's settled-state
  // checks, so an invented possession («弗里嘉演习弹在手中发烫»), a re-enacted
  // appearance or an item acting as a person passed. These compare the prose
  // with the scene's settled descriptions; they are not word lists.
  // Licensed quotes are someone else's words (the rule board says 护目镜必须戴好):
  // reading them as the narrator's own claim is the aa30 false positive.
  const quoteMasked = scene.licensed.quotes.reduce((value, quote) => (
    quote.length >= 4 ? value.split(quote).join('「」') : value
  ), text);
  const settledViolations = settledViolationsFromScene(quoteMasked, {
    inputText: scene.inputText,
    place: { name: scene.place.name, note: scene.place.note },
    present: scene.present.map((person) => ({ name: person.name, note: person.note })),
    objects: scene.objects.map((object) => ({ name: object.name, note: object.note })),
    viewpoint: { name: scene.viewpoint.name, note: scene.viewpoint.note },
  }, [...scene.licensed.names, scene.viewpoint.name]);
  // A sentence that reproduces a settled scene description («牌面写明：…护目镜
  // 必须戴好») is quoting the scene, not making a new claim: the appearance checks
  // read a rule-board line as the narrator wearing the goggles (aa30/this test).
  const settledDetails = [...scene.licensed.details, ...scene.licensed.quotes].filter((detail) => detail.length >= 6);
  const quotesSettled = (sentence: string) => settledDetails.some((detail) => sentence.includes(detail) || detail.includes(sentence));
  for (const violation of settledViolations) {
    if (quotesSettled(violation.sentence)) continue;
    issues.push({ kind: 'unlicensed_event', severity: 'hard', beatId: null, detail: violation.detail, sentence: violation.sentence });
  }

  // ---- 3. licensing ---------------------------------------------------------
  const licensedNames = [...scene.licensed.names, ...scene.licensed.locations, ...scene.licensed.items,
    ...scene.licensed.details, ...scene.licensed.quotes];
  const mask = licenseMask(text, licensedNames);
  const detailText = [...scene.licensed.details, ...scene.licensed.quotes,
    scene.place.note, scene.viewpoint.note, ...scene.present.map((person) => person.note),
    ...scene.objects.map((object) => object.note)].join('；');
  const allNames = [...new Set([
    ...scene.worldNames.characters, ...scene.worldNames.locations, ...scene.worldNames.items,
  ])].sort((left, right) => right.length - left.length);
  // A place or object the settled scene text itself names (the route map note
  // lists 西回廊/检修口) is a known name, not an unlicensed entity: naming it is
  // describing the scene. Claiming to have gone there still needs a move fact.
  const knownFromScene = new Set([...scene.worldNames.locations, ...scene.worldNames.items]
    .filter((name) => name.length >= 2 && detailText.includes(name)));
  for (const name of allNames) {
    if (knownFromScene.has(name)) continue;
    const hit = unlicensedName(text, name, mask);
    if (hit) {
      issues.push({ kind: 'unlicensed_entity', severity: 'hard', beatId: null, detail: hit });
      break;
    }
  }

  const allowedNumbers = new Set<number>();
  for (const value of numbersIn([scene.licensed.details.join('；'), scene.licensed.quotes.join('；')].join('；'))) allowedNumbers.add(value);
  if (scene.time) {
    allowedNumbers.add(scene.time.duration.amount);
  }
  for (const fact of scene.facts) {
    if (fact.kind === 'sanity_changed') { allowedNumbers.add(fact.from); allowedNumbers.add(fact.to); }
  }
  for (const value of numbersIn(text)) {
    if (!allowedNumbers.has(value)) {
      issues.push({ kind: 'fact_wrong_number', severity: 'hard', beatId: null, detail: `number ${value} is not licensed` });
      break;
    }
  }

  const knownItems = new Set(scene.knowledge.discoveredItemIds);
  for (const sentence of parts) {
    if (!REDISCOVERY.test(sentence)) continue;
    for (const fact of scene.facts) {
      if (fact.kind !== 'item_present' && fact.kind !== 'item_discovered') continue;
      if (sentence.includes(fact.name) && knownItems.has(fact.itemId)) {
        issues.push({ kind: 'rediscovery_claim', severity: 'hard', beatId: null, detail: fact.name, sentence });
      }
    }
  }

  for (const sentence of parts) {
    if (!PRIVATE_THOUGHT.test(sentence)) continue;
    for (const name of presentNames) {
      if (sentence.includes(name)) {
        issues.push({ kind: 'perspective_leak', severity: 'hard', beatId: null, detail: `${name} 的内心`, sentence });
        break;
      }
    }
  }

  for (const term of options.forbiddenKnowledge ?? []) {
    if (term && text.includes(term)) {
      issues.push({ kind: 'perspective_leak', severity: 'hard', beatId: null, detail: `forbidden knowledge: ${term}` });
    }
  }

  if (PROMPT_ECHO.test(text)) {
    issues.push({ kind: 'prompt_echo', severity: 'hard', beatId: null, detail: 'text repeats prompt material' });
  }

  const lines = text.split(NEWLINES).map((line) => line.trim()).filter(Boolean);
  if (lines.some((line) => FACT_LIST_LINE.test(line) || FACT_LABEL.test(line))) {
    issues.push({ kind: 'fact_list', severity: 'hard', beatId: null, detail: 'bullet/label list is not prose' });
  }

  // Chinese prose: Latin letters are only allowed when they are part of a
  // licensed name (e.g. a mixed-script item name).
  const latin = (text.match(/[A-Za-z]/gu) ?? []).length;
  const cjk = (text.match(/[一-鿿]/gu) ?? []).length;
  if (latin > 6 && latin * 3 > cjk) {
    issues.push({ kind: 'off_language', severity: 'hard', beatId: null, detail: `letters ${latin} vs CJK ${cjk}` });
  }

  // ---- 4. shape ------------------------------------------------------------
  const minChars = options.minChars ?? 0;
  const maxChars = options.maxChars ?? Number.POSITIVE_INFINITY;
  if (chars < minChars) issues.push({ kind: 'too_short', severity: 'hard', beatId: null, detail: `${chars} < ${minChars}` });
  if (chars > maxChars) issues.push({ kind: 'too_long', severity: 'hard', beatId: null, detail: `${chars} > ${maxChars}` });

  const seen = new Map<string, number>();
  for (const sentence of parts) {
    const key = stripEnd(sentence);
    if (!key) continue;
    seen.set(key, (seen.get(key) ?? 0) + 1);
  }
  for (const [sentence, count] of seen) {
    if (count > 1) issues.push({ kind: 'repeated_sentence', severity: 'hard', beatId: null, detail: sentence });
  }

  const repetition = options.checkPrior === false ? null : repetitionAgainst(text, options.priorText ?? null);
  // Bigram overlap is naturally high on very short turns (shared names and
  // place words); only demand a low ratio once both turns carry real prose.
  const repetitionCap = chars < 200 || (options.priorText ?? '').length < 200 ? 0.75 : 0.5;
  if (repetition != null && repetition > repetitionCap) {
    issues.push({ kind: 'echo_prior', severity: 'soft', beatId: null, detail: `bigram overlap ${repetition.toFixed(2)}` });
  }

  // Unverified sentences: bind nothing, but claim no new event/entity/number.
  const eventVerbs = EVENT_VERBS.filter((verb) => text.includes(verb));
  const unverifiedSentences: string[] = [];
  const boundIds = new Set(coverage.filter((entry) => entry.expressed).map((entry) => entry.factId));
  for (const sentence of parts) {
    const bindsSomething = scene.facts.some((fact) => {
      if (!boundIds.has(fact.id)) return false;
      if (fact.kind === 'move') return sentence.includes(fact.from) && sentence.includes(fact.to);
      if (fact.kind === 'task_achieved' || fact.kind === 'subtask_added') return sentence.includes(stripEnd(fact.goal));
      if (fact.kind === 'personality_changed') return sentence.includes(stripEnd(fact.text));
      if (fact.kind === 'appearance_changed') return sentence.includes(stripEnd(fact.text ?? ''));
      if (fact.kind === 'sanity_changed') return sentence.includes(fact.name);
      if (fact.kind === 'item_present' || fact.kind === 'item_discovered') return sentence.includes(fact.name);
      if (fact.kind === 'at') return sentence.includes(fact.name);
      if (fact.kind === 'time') return mentionsTime(sentence, { amount: fact.advance.duration.amount, unit: fact.advance.duration.unit });
      return false;
    });
    if (bindsSomething) continue;
    const masked = maskLicensed(sentence, [...scene.licensed.details, ...scene.licensed.quotes]);
    if (eventVerbs.some((verb) => masked.includes(verb))) continue;
    if (numbersIn(sentence).some((value) => !allowedNumbers.has(value))) continue;
    // A sentence that is entirely settled description is grounded, not
    // unverified: the licence mask removed all of its content.
    if (masked.replace(/[＿\s，。！？；：]/gu, '').length < 2) continue;
    unverifiedSentences.push(sentence);
  }

  const ok = !issues.some((issue) => issue.severity === 'hard');
  return { ok, coverage, issues, unverifiedSentences, chars, repetition };
}

/** Compact per-beat gate used before accepting a composer's beat text. */
export function verifyBeatText(
  text: string,
  beat: { id: string; factIds: string[] },
  options: Omit<VerifyOptions, 'factIds' | 'minChars' | 'maxChars' | 'checkPrior'>,
): CandidateIssue[] {
  const result = verifyText(text, {
    ...options,
    factIds: beat.factIds,
    minChars: 0,
    maxChars: Number.POSITIVE_INFINITY,
    checkPrior: false,
  });
  return result.issues.map((issue) => ({ ...issue, beatId: beat.id }));
}

export type { EntityDelta, FactVisibility, Id, TimeAdvance };
