/** Post-generation verification.
 *
 * Two layers, both read-only:
 *  1. the existing sentence-scoped fact-alignment grader (`alignNarration`)
 *     decides whether a sentence contradicts a committed fact;
 *  2. this file adds the checks the grader does not own — mandatory-fact
 *     coverage, required time, viewpoint interiority, hidden knowledge,
 *     unlicensed names, cross-turn echo, in-draft loops, truncation and
 *     premature closure.
 *
 * A hard issue rejects a draft. An `unverified_sentence` is soft evidence: the
 * grader's own design says out-of-vocabulary wording is a review flag, not a
 * fabrication verdict. Both are returned so the page/evidence never hides
 * what the model wrote.
 */
import type { CommittedNarration, NarrationFact } from '../../runtime/committed-narration';
import { factPhrases } from '../../runtime/committed-narration';
import { alignNarration, numbersIn, type AlignmentResult } from '../../runtime/narration-alignment';
import type { NarrationIssue, NarrationIssueKind, NarrationLedger, NarrationMetrics, NarrationPolicy } from './types';
import { PAST_MARKERS, PROMISE_VERBS } from './ledger';

const ALIGNMENT_KINDS: Record<string, NarrationIssueKind> = {
  actor_swap: 'fact_actor_swap',
  direction_reversed: 'fact_direction_reversed',
  wrong_number: 'fact_wrong_number',
  wrong_time: 'fact_wrong_time',
  task_claimed_without_fact: 'fact_task_claimed',
  movement_without_fact: 'fact_movement_claimed',
  state_claim_without_fact: 'fact_position_claimed',
  added_event: 'fact_event_added',
  empty_narration: 'empty_narration',
};

/** Interiority / knowledge verbs. A non-POV character must not be narrated
 * with these: only the viewpoint character's inner life is visible. */
const INTERIOR = /(心想|暗想|心里|心中|内心|暗自|默默|感到|觉得|意识到|知道|记得|明白|盘算|打算|决定|希望|害怕|担心|后悔|犹豫|松了口气)/u;
const TERMINAL = /[\u3002\uff01\uff1f!?\u2026\u201d\u300d\u300f.~～)\uff09]$/u;
const CLOSURE = /(故事|这一天|这一夜|今晚|一切|夜色|人群|喧闹)[^。！？]{0,12}(结束|落幕|告一段落|过去|平静|散去|画上)/u;
const FAREWELL = /(后来|从此)[，,]?[^。！？]{0,12}(没有|不再|归于)/u;
const SENTENCE_SPLIT = /[。！？\n]+/u;
const CLAUSE_SPLIT = /[。！？；，,、\n]+/u;
const NEGATION = '(?:没有|没|未|不曾|并未|未曾|并不)';
const SANITY_CONTEXT = /(精神|理智|清醒|值|变|升|降|掉|减|增|恢复|回落|涨)/u;
/** A numeric transition (从十降到八), not a movement (从走廊走到门厅). */
const NUMERIC_TRANSITION = /(?:从|由)\s*(?:[0-9]+|[零一二三四五六七八九十两]+)\s*(?:升|降|变|到|至)/u;
const escapeRegExp = (value: string): string => value.replace(/[.*+?^${}()|[\]\\]/gu, '\\$&');

export interface VerifyInput {
  text: string;
  finishReason: string | null;
  committed: CommittedNarration;
  ledger: NarrationLedger;
  policy: NarrationPolicy;
  priorText: string | null;
  attempt: number;
  /** Strings that prove the model copied instructions into the prose. */
  promptEchoMarkers?: string[];
}

export interface VerifyOutput {
  issues: NarrationIssue[];
  alignment: AlignmentResult | null;
  metrics: NarrationMetrics;
}

const hard = (kind: NarrationIssueKind, attempt: number, detail: string, sentence?: string): NarrationIssue =>
  ({ kind, severity: 'hard', attempt, detail, ...(sentence ? { sentence } : {}) });
const soft = (kind: NarrationIssueKind, attempt: number, detail: string, sentence?: string): NarrationIssue =>
  ({ kind, severity: 'soft', attempt, detail, ...(sentence ? { sentence } : {}) });

const charsOf = (text: string): number => [...text].length;
const sentencesOf = (text: string): string[] => text.split(SENTENCE_SPLIT).map((part) => part.trim()).filter(Boolean);
const normalize = (text: string): string => text.replace(/[\s，。！？；：、「」『』“”"'…—\-·]/gu, '');
const dialogueShare = (text: string): number => {
  const chars = charsOf(text);
  if (!chars) return 0;
  let inside = 0;
  for (const match of text.matchAll(/「[^」]*」/gu)) inside += charsOf(match[0]);
  return inside / chars;
};

export function verifyNarration(input: VerifyInput): VerifyOutput {
  const { text, ledger, policy, attempt, finishReason, priorText } = input;
  const issues: NarrationIssue[] = [];
  const chars = charsOf(text);
  const sentences = sentencesOf(text);
  const duration = ledger.time?.duration ?? null;
  const alignment = chars > 0
    ? alignNarration(input.committed, text, {
      time: duration,
      previousText: priorText,
      roster: policy.roster ?? ledger.actorNames,
      locations: policy.locations,
      knownPositions: policy.knownPositions,
      // Time coverage is reported by `alignment.timeExpressed` and judged
      // below with the ledger's explicit rule; `alignment.ok` is not used.
      requireTime: false,
    })
    : null;

  if (!chars) issues.push(hard('empty_narration', attempt, 'empty or whitespace-only narration'));

  const sanitySentences: string[] = [];
  for (const violation of alignment?.violations ?? []) {
    // The base grader has no "player action licensed this verb" option. A
    // committed action like 推开 the door licenses exactly that verb for this
    // point; the detail carries the verb, so no second verb list is created.
    const verb = violation.kind === 'added_event'
      ? /event verb (\S+) has no committed fact/u.exec(violation.detail)?.[1]
      : undefined;
    if (verb && ledger.allowedEvents.includes(verb)) continue;
    // A negated event («没有推开门») does not assert that it happened. The
    // grader explicitly does not model negation; this local filter only
    // removes the violation when the negation sits directly on the verb.
    if (verb && new RegExp(`${NEGATION}\\s*${escapeRegExp(verb)}`, 'u').test(violation.sentence)) continue;
    // The grader's movement verb list contains 到, so «从十降到八» reads as a
    // movement from the at-fact's location. It is a stat transition; judge the
    // numbers below instead of charging an invented move.
    if (violation.kind === 'movement_without_fact'
      && SANITY_CONTEXT.test(violation.sentence) && NUMERIC_TRANSITION.test(violation.sentence)) {
      sanitySentences.push(violation.sentence);
      continue;
    }
    // `numbersIn` reads any Chinese numeral after 从/到/是/为/至. In a scene
    // sentence that also names a character («周宁接过来，是一本旧书») that is
    // not a sanity claim; only keep the violation when the sentence talks
    // about the stat or a change.
    if (violation.kind === 'wrong_number' && !SANITY_CONTEXT.test(violation.sentence)) continue;
    issues.push(hard(ALIGNMENT_KINDS[violation.kind] ?? 'fact_event_added', attempt, violation.detail, violation.sentence));
  }
  // Restore the numeric check the movement short-circuit skipped: a stat
  // transition must use the committed from/to (or the static value).
  for (const sentence of sanitySentences) {
    const numbers = numbersIn(sentence);
    for (const fact of input.committed.facts) {
      if (fact.kind !== 'sanity' && fact.kind !== 'sanity_changed') continue;
      if (!sentence.includes(fact.name)) continue;
      const allowed = fact.kind === 'sanity' ? [fact.value] : [fact.from, fact.to];
      const wrong = numbers.find((value) => !allowed.includes(value));
      if (wrong !== undefined) {
        issues.push(hard('fact_wrong_number', attempt, `${fact.name}: ${wrong} not in [${allowed.join(', ')}]`, sentence));
        break;
      }
    }
  }

  // Mandatory coverage: a settled change whose only trace is the state panel
  // is not narrated. Static backdrop facts stay optional (no roll-call).
  const expressed = new Set((alignment?.coverage ?? []).filter((entry) => entry.expressed).map((entry) => entry.id));
  for (const fact of ledger.mandatory) {
    if (!expressed.has(fact.id)) {
      issues.push(hard('fact_omitted', attempt, factPhrases(fact)[0], undefined));
    }
  }

  if (ledger.requireTime && duration && (alignment === null || alignment.timeExpressed === false)) {
    issues.push(hard('time_missing', attempt, `required ${duration.amount} ${duration.unit}`));
  }

  // Fabricated continuity: a promise or a strong past reference that is not
  // present in the serialized input, the previous accepted prose, or the
  // caller's explicit license. This is the class of failure the baseline
  // showed ("小时候从树上掉下来", a promise the input never made).
  for (const sentence of sentences) {
    const promise = PROMISE_VERBS.find((verb) => sentence.includes(verb) && !ledger.licensedPromises.includes(verb));
    if (promise) {
      issues.push(hard('promise_without_fact', attempt, `promise verb ${promise} has no committed or prior source`, sentence));
    }
    const past = PAST_MARKERS.find((marker) => sentence.includes(marker) && !ledger.licensedPastMarkers.includes(marker));
    if (past) {
      issues.push(hard('past_without_fact', attempt, `past marker ${past} has no committed or prior source`, sentence));
    }
  }

  const minChars = policy.minChars ?? 120;
  if (chars > 0 && chars < minChars) issues.push(hard('too_short', attempt, `${chars} < ${minChars} characters`));
  if (finishReason === 'length') {
    issues.push(hard('truncated', attempt, 'generation stopped at the token limit'));
  } else if (chars >= 40 && !TERMINAL.test(text.trim())) {
    issues.push(hard('truncated', attempt, 'narration does not end at a sentence boundary'));
  }

  const targetChars = policy.targetChars ?? 260;
  const last = sentences.at(-1) ?? '';
  if (chars > 0 && chars < targetChars * 0.6 && (CLOSURE.test(last) || FAREWELL.test(last))) {
    issues.push(hard('premature_closure', attempt, 'scene closes before the target length', last));
  }

  // Beat mode sets an explicit per-beat ceiling; whole-scene mode leaves it
  // undefined so a long scene is not rejected for being long.
  if (policy.beatMaxChars !== undefined && chars > policy.beatMaxChars) {
    issues.push(hard('too_long', attempt, `${chars} > ${policy.beatMaxChars} characters`));
  }

  const maxOverlap = policy.maxPriorOverlap ?? 0.55;
  if (alignment?.repetition != null && alignment.repetition > maxOverlap) {
    issues.push(hard('echo_prior', attempt, `bigram overlap ${alignment.repetition.toFixed(2)} > ${maxOverlap}`));
  }

  // In-draft loops: the observed small-model failure was the same sentence
  // three or four times. Compare punctuation-stripped text so a comma change
  // cannot hide a loop.
  const normalizedSentences = sentences.map(normalize).filter((entry) => entry.length >= 4);
  const sentenceCount = new Map<string, number>();
  for (const entry of normalizedSentences) sentenceCount.set(entry, (sentenceCount.get(entry) ?? 0) + 1);
  const repeatedSentences = [...sentenceCount.entries()].filter(([, count]) => count >= 2);
  for (const [entry] of repeatedSentences) {
    issues.push(hard('loop_repeated_sentence', attempt, `sentence repeated ${sentenceCount.get(entry)}x`, entry.slice(0, 80)));
  }
  const clauses = text.split(CLAUSE_SPLIT).map(normalize).filter((entry) => entry.length >= 8);
  const clauseCount = new Map<string, number>();
  for (const entry of clauses) clauseCount.set(entry, (clauseCount.get(entry) ?? 0) + 1);
  const repeatedClauses = [...clauseCount.entries()].filter(([entry, count]) => count >= 3
    && !repeatedSentences.some(([sentence]) => sentence.includes(entry)));
  for (const [entry, count] of repeatedClauses) {
    issues.push(hard('loop_repeated_clause', attempt, `clause repeated ${count}x`, entry.slice(0, 80)));
  }

  if (ledger.viewpoint) {
    const pov = ledger.viewpoint.name;
    const names = [...new Set([...(policy.roster ?? []), ...ledger.actorNames])].filter((name) => name !== pov && name.length >= 1);
    for (const sentence of sentences) {
      const narration = sentence.replace(/「[^」]{0,300}」/gu, '「」');
      for (const name of names) {
        const index = narration.indexOf(name);
        if (index < 0) continue;
        // Scope: from this name to the next roster name in the sentence, so
        // “林川走过去，周宁心里一沉” does not charge 林川 with 周宁's thought.
        const tail = narration.slice(index + name.length);
        const next = names.filter((other) => other !== name)
          .map((other) => tail.indexOf(other)).filter((position) => position >= 0)
          .sort((a, b) => a - b)[0];
        const scope = next === undefined ? tail : tail.slice(0, next);
        if (INTERIOR.test(scope)) {
          issues.push(hard('perspective_leak', attempt, `${name} interiority outside ${pov}'s viewpoint`, sentence));
        }
      }
    }
  }

  for (const secret of ledger.forbiddenKnowledge) {
    if (secret.length >= 2 && text.includes(secret)) {
      issues.push(hard('knowledge_leak', attempt, 'hidden knowledge surfaced in the prose'));
    }
  }

  const licensed = new Set(ledger.licensedEntities);
  for (const name of policy.knownEntities ?? []) {
    if (name.length < 2 || licensed.has(name)) continue;
    // A shorter name inside a licensed longer name is not a separate mention
    // (钟楼 vs 钟楼西门); prefer avoiding a false rejection.
    if ([...licensed].some((entry) => entry.includes(name))) continue;
    if (text.includes(name)) {
      issues.push(hard('unlicensed_entity', attempt, `${name} is in no committed fact or licensed context`));
    }
  }

  for (const marker of input.promptEchoMarkers ?? []) {
    if (marker && text.includes(marker)) {
      issues.push(hard('prompt_echo', attempt, 'model copied the writing instructions into the prose'));
      break;
    }
  }

  for (const sentence of alignment?.unverified ?? []) {
    issues.push(soft('unverified_sentence', attempt, 'sentence binds no committed fact and contradicts none', sentence));
  }

  const metrics: NarrationMetrics = {
    chars,
    sentences: sentences.length,
    paragraphs: text.split(/\n\s*\n/u).filter((part) => part.trim()).length,
    dialogueRatio: dialogueShare(text),
    mandatoryFacts: ledger.mandatory.length,
    mandatoryExpressed: ledger.mandatory.filter((fact) => expressed.has(fact.id)).length,
    unverifiedSentences: alignment?.unverified.length ?? 0,
    echoRatio: alignment?.repetition ?? null,
    repeatedSentences: repeatedSentences.length,
    repeatedClauses: repeatedClauses.length,
  };
  return { issues, alignment, metrics };
}

/** Facts whose text may be quoted verbatim in repair guidance. Only committed
 * facts enter; never a model sentence and never hidden knowledge. */
export function guidanceFacts(facts: readonly NarrationFact[], limit = 3): string[] {
  return facts.slice(0, limit).map((fact) => factPhrases(fact)[0]);
}
