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
import { objectActorViolations, settledAppearanceViolations, settledStateViolations } from './licensed-sense';

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
  /** The serialized input the model was given. Needed where a check compares
   * the prose with a settled line (hair, worn items) rather than with a fact. */
  inputText?: string;
}

export interface VerifyOutput {
  issues: NarrationIssue[];
  alignment: AlignmentResult | null;
  metrics: NarrationMetrics;
}

/** A settled sanity/personality change can be shown through a concrete
 * reaction instead of the grader's literal number or trait phrase. This is an
 * expression-form allowance, not a fact allowance: the name and a visible
 * change marker are required, the sanity direction is checked when the prose
 * states one, and every natural expression is returned as a soft review flag.
 * Moved/task/time facts still require their checkable content. */
type NaturalFact = { sentence: string; direction?: 'match' | 'wrong' | 'unstated' };
const BODY_REACTION = /(呼吸|手指|手|声音|视线|肩|脸色|脚步|膝盖|背|眼|喉|胸口|心跳|沉默|坐|站|扶|攥|捏|握|松开|垂下|抬起|移开|闭|睁|笑|皱眉)/u;
const CHANGE_MARKER = /(比刚才|比平时|下来|起来|少了|多了|慢|快|浅|沉|稳|轻|紧|松|抬|垂|移开|停|颤|不再|第一次|这次|顿了顿|停了停)/u;
const SANITY_UP = /(稳|轻|松|暖|亮|快|强|舒|匀|平静|缓|直|好|清明)/u;
const SANITY_DOWN = /(沉|低|乱|紧|冷|抖|弱|慢|重|浅|急|暗|退|缩|空|木)/u;
const TRAIT_BEHAVIOUR = /(说|问|答|笑|看|望|停|让|接|推|收|放|走|站|坐|转|低|抬|摇|点|沉默|没有|不再|第一次|这次)/u;

function naturalFactExpression(fact: NarrationFact, sentences: readonly string[]): NaturalFact | null {
  if (fact.kind !== 'sanity_changed' && fact.kind !== 'personality_changed') return null;
  for (const sentence of sentences) {
    if (!sentence.includes(fact.name)) continue;
    if (!BODY_REACTION.test(sentence) && !TRAIT_BEHAVIOUR.test(sentence)) continue;
    if (!CHANGE_MARKER.test(sentence)) continue;
    if (fact.kind === 'personality_changed') return { sentence };
    const up = SANITY_UP.test(sentence);
    const down = SANITY_DOWN.test(sentence);
    if (!up && !down) return { sentence, direction: 'unstated' };
    const rose = fact.to > fact.from;
    if ((rose && down && !up) || (!rose && up && !down)) return { sentence, direction: 'wrong' };
    return { sentence, direction: 'match' };
  }
  return null;
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

/** Content words of a task goal, used to accept a paraphrase instead of the
 * exact sentence. Drops numbers, measure words and connectives. */
function goalKeyTerms(goal: string): string[] {
  const stopChars = new Set(['的', '了', '一', '二', '三', '四', '五', '六', '七', '八', '九', '十', '两', '几',
    '份', '本', '个', '件', '条', '些', '把', '和', '与', '或', '在', '里', '上', '下']);
  const terms: string[] = [];
  // Bigrams of the goal keep a paraphrase like «比对完毕» connected to
  // «比对三份互相矛盾的登记簿» without demanding the whole phrase.
  for (let i = 0; i + 2 <= goal.length; i += 1) {
    const term = goal.slice(i, i + 2);
    if ([...term].some((char) => stopChars.has(char))) continue;
    if ([...term].every((char) => /[a-zA-Z0-9]/u.test(char))) continue;
    if (!terms.includes(term)) terms.push(term);
  }
  return terms;
}

export function verifyNarration(input: VerifyInput): VerifyOutput {
  const { text, ledger, policy, attempt, finishReason, priorText } = input;
  const inputText = input.inputText ?? '';
  const issues: NarrationIssue[] = [];
  const chars = charsOf(text);
  const sentences = sentencesOf(text);
  const duration = ledger.time?.duration ?? null;
  // Static `at` facts are scene context, not assertions: the upstream actor
  // attribution treats a leading location name as the actor and reports a
  // false actor swap, and its at-fact movement guard reads a location's
  // weather clause as the character moving. Positions still license standing
  // claims through knownPositions.
  const atFacts = input.committed.facts.filter((fact) => fact.kind === 'at');
  const alignmentPacket = { ...input.committed, facts: input.committed.facts.filter((fact) => fact.kind !== 'at') };
  const alignmentPositions = [
    ...(policy.knownPositions ?? []),
    ...atFacts.map((fact) => ({ name: fact.name, location: fact.location })),
  ];
  // The upstream grader treats only 。！？ as sentence boundaries. A semicolon
  // is a clause boundary in the short-scene corpus (two actors, two commits);
  // normalizing it prevents the second clause's name from being read as an
  // actor swap in the first. Display/evidence keep the original text.
  const alignmentText = text.replace(/[；;]/gu, '。');
  const alignment = chars > 0
    ? alignNarration(alignmentPacket, alignmentText, {
      time: duration,
      previousText: priorText,
      roster: policy.roster ?? ledger.actorNames,
      locations: policy.locations,
      knownPositions: alignmentPositions,
      // Time coverage is reported by `alignment.timeExpressed` and judged
      // below with the ledger's explicit rule; `alignment.ok` is not used.
      requireTime: false,
    })
    : null;

  if (!chars) issues.push(hard('empty_narration', attempt, 'empty or whitespace-only narration'));

  const sanitySentences: string[] = [];
  // Sentences whose only alignment violation was a false-positive number
  // («一张纸条» read as sanity 1). The alignment loop `continue`s after a
  // number violation, so a real event verb in the same sentence is never
  // checked; re-run those sentences with the fact packet stripped so only the
  // event/state rules fire.
  const recheckSentences: string[] = [];
  for (const violation of alignment?.violations ?? []) {
    // The base grader's duration scanner finds 10 inside 二十 and finds a
    // year in 九八年; when the required elapsed duration itself is present,
    // those are not contradictions. A missing/wrong duration still fails via
    // time_missing below.
    if (violation.kind === 'wrong_time' && alignment?.timeExpressed === true) continue;
    // 天台 is a prefix of 天台楼梯间. The upstream's location-proximity check
    // reports the shorter name even when the committed move ends at the longer
    // one; the moved fact licenses that sentence.
    if (violation.kind === 'movement_without_fact') {
      const claim = /^claims movement involving (.+)$/u.exec(violation.detail)?.[1];
      const moved = claim ? input.committed.facts.find((fact) => fact.kind === 'moved'
        && (fact.to === claim || fact.to.startsWith(claim) || fact.from === claim)
        && violation.sentence.includes(fact.name) && violation.sentence.includes(fact.to)) : undefined;
      if (moved) continue;
    }
    // A sentence can carry two characters: «A办完了…；B的精神值从41升到46».
    // The upstream sanity check sees A + 41 and charges A with the wrong
    // number. If another sanity fact in the same sentence licenses 41, the
    // number belongs to that character.
    if (violation.kind === 'wrong_number') {
      const match = /^(\S+): ([0-9]+) not in/u.exec(violation.detail);
      if (match) {
        const number = Number(match[2]);
        const other = input.committed.facts.find((fact) => (fact.kind === 'sanity' || fact.kind === 'sanity_changed')
          && fact.name !== match[1] && violation.sentence.includes(fact.name)
          && (fact.kind === 'sanity' ? fact.value === number : [fact.from, fact.to].includes(number)));
        if (other) continue;
      }
    }
    // A committed personality sentence can contain another character's name
    // («答应陪周含章...»). The name inside the frozen text is not actor swap.
    if (violation.kind === 'actor_swap') {
      const id = /payload of (\S+) attributed to/u.exec(violation.detail)?.[1];
      const fact = id ? input.committed.facts.find((entry) => entry.id === id) : undefined;
      if (fact?.kind === 'personality_changed' && text.includes(fact.text)) continue;
      if (fact?.kind === 'task_achieved') {
        const beforeCompletion = violation.sentence.split(/(?:办完|完成|做完|搞定|达成|结束|办妥|了结)/u)[0] ?? '';
        const jointSubject = /(?:、|和|与|跟)/u.test(beforeCompletion) && beforeCompletion.includes(fact.name);
        if (jointSubject && violation.sentence.includes(fact.goal)) continue;
      }
    }
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
    if (violation.kind === 'wrong_number' && !SANITY_CONTEXT.test(violation.sentence)) {
      recheckSentences.push(violation.sentence);
      continue;
    }
    issues.push(hard(ALIGNMENT_KINDS[violation.kind] ?? 'fact_event_added', attempt, violation.detail, violation.sentence));
  }
  // Second pass over the dismissed sentences: no facts means no numeric
  // shortcut, so an event verb in them is reported instead of being lost.
  for (const sentence of [...new Set(recheckSentences)]) {
    const bare = alignNarration({ ...input.committed, facts: [] }, sentence, {
      time: null, previousText: null, roster: policy.roster ?? ledger.actorNames,
      locations: policy.locations, knownPositions: policy.knownPositions, requireTime: false,
    });
    for (const violation of bare.violations) {
      if (violation.kind !== 'added_event') continue;
      const verb = /event verb (\S+) has no committed fact/u.exec(violation.detail)?.[1];
      if (verb && ledger.allowedEvents.includes(verb)) continue;
      if (verb && new RegExp(`${NEGATION}\\s*${escapeRegExp(verb)}`, 'u').test(sentence)) continue;
      issues.push(hard('fact_event_added', attempt, violation.detail, sentence));
    }
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
    if (expressed.has(fact.id)) continue;
    // A pronoun / comma-spanning move («A离开天台，走进天台楼梯间») can defeat
    // the sentence-scoped arrival regex. Both endpoints and the actor name in
    // the text keep the content; direction_reversed still rejects a reversed
    // move, and this is a soft actor-binding review, not a keyword pass.
    if (fact.kind === 'moved' && text.includes(fact.name) && text.includes(fact.from) && text.includes(fact.to)
      && /(从|离开|自|走到|走向|走进|来到|进|到|去)/u.test(text)) {
      expressed.add(fact.id);
      issues.push(soft('unverified_sentence', attempt,
        `movement endpoints quoted; actor binding needs review`, undefined));
      continue;
    }
    // A pronoun subject («她...») can hide the actor from sentence-scoped
    // coverage. The frozen goal/personality text itself is the fact content:
    // when it appears verbatim and the actor's name is in the scene, keep the
    // content but flag the actor binding for review. Moved/task time still
    // need the alignment; this is not a keyword-only pass.
    // Paraphrase: the run that completed «比对三份互相矛盾的登记簿» wrote
    // «将三本簿子比对完毕» and was still failed for the literal goal string.
    // A task is expressed when the actor, a key term from the goal and a
    // completion cue are all present, so the content is kept without demanding
    // a verbatim quote.
    if (fact.kind === 'task_achieved' && text.includes(fact.name)) {
      const keys = goalKeyTerms(fact.goal).filter((term) => text.includes(term));
      const done = /(办完|完成|做完|搞定|达成|结束|办妥|了结|完毕|对上|查清|核清|对完|看完|翻完)/u.test(text);
      if (keys.length && done) {
        expressed.add(fact.id);
        issues.push(soft('unverified_sentence', attempt,
          `task result paraphrased (${keys.join('、')}); actor binding needs review`, undefined));
        continue;
      }
    }
    if (fact.kind === 'task_achieved' && text.includes(fact.goal) && text.includes(fact.name)
      && /(办完|完成|做完|搞定|达成|结束|办妥|了结)/u.test(text)) {
      expressed.add(fact.id);
      issues.push(soft('unverified_sentence', attempt,
        `task goal quoted; actor binding needs review`, undefined));
      continue;
    }
    if (fact.kind === 'personality_changed' && text.includes(fact.text) && text.includes(fact.name)) {
      expressed.add(fact.id);
      issues.push(soft('unverified_sentence', attempt,
        `personality text quoted; actor binding needs review`, undefined));
      continue;
    }
    const natural = naturalFactExpression(fact, sentences);
    if (natural?.direction === 'wrong') {
      issues.push(hard('fact_wrong_number', attempt,
        `${factPhrases(fact)[0]} (natural direction contradicts the committed change)`, natural.sentence));
      continue;
    }
    if (natural) {
      expressed.add(fact.id);
      issues.push(soft('unverified_sentence', attempt,
        `${fact.kind} shown through a reaction; human review required`, natural.sentence));
      continue;
    }
    issues.push(hard('fact_omitted', attempt, factPhrases(fact)[0], undefined));
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

  // Length is not a pass/fail criterion on its own. The product allows a turn
  // to be shorter when nothing big happened, as long as it still says what
  // changed. Below two thirds of the contract the text stops reading as prose,
  // and that stays hard; between there and the contract it is a soft note.
  // A passage that says «他手中的护目镜…» and later «手中没有拿任何东西» is
  // contradicting itself; the page's accepted 185-character turn did exactly
  // that. This is not a fact check against the input — it needs no input at all.
  {
    const sentences = text.split(/(?<=[。！？!?])|\n+/u).map((sentence) => sentence.trim()).filter(Boolean);
    const HAND = /(手中|手里|手上)/u;
    const EMPTY = /(没有|没|空着|空空|什么也没有|什么也没拿)/u;
    let held: string | null = null;
    for (const sentence of sentences) {
      if (!HAND.test(sentence)) continue;
      if (EMPTY.test(sentence)) {
        if (held) {
          issues.push(hard('self_contradiction', attempt,
            `text first says ${held} is in the hand, then says the hand is empty`, sentence));
        }
        continue;
      }
      const clause = sentence.split(/[，,；;]/u).find((part) => HAND.test(part)) ?? sentence;
      held = clause.slice(0, 24);
    }
    // The same object cannot be in a hand and hanging at the waist. 09's e9a5
    // turn wrote «她手中的短枪还挂在腰间» in one sentence.
    const WEAR = /(挂在|系在|插在|别在|放在|贴在)(腰间|腰上|背上|肩上|墙上|桌上|地上)/u;
    for (const sentence of sentences) {
      const inHand = /(?:手中|手里|手上)的?([一-龥]{2,4}?)(?=[还正已就，。；、]|$)/u.exec(sentence);
      if (!inHand) continue;
      const wear = WEAR.exec(sentence);
      if (!wear || wear.index < inHand.index) continue;
      const noun = inHand[1];
      if (sentence.lastIndexOf(noun, wear.index) < 0) continue;
      issues.push(hard('self_contradiction', attempt,
        `text says ${noun} is in the hand and also ${wear[1]}${wear[2]}`, sentence));
    }
  }

  // 01's independent read of the 2026-11-10 route batch found three bindings the
  // automatic verifier missed: another person's settled hair colour on the
  // viewpoint, tied hair rewritten as loose, and goggles settled on the chest
  // treated as worn. Each is a contradiction with the serialized input.
  {
    const names = policy.roster ?? policy.scene?.present?.map((person) => person.name) ?? [];
    for (const violation of settledAppearanceViolations(text, inputText, names.filter(Boolean), policy.scene?.inventory ?? [])) {
      issues.push(hard('self_contradiction', attempt, violation.detail, violation.sentence));
    }
  }

  // Re-enacted settled states and an accessory used as an actor: 01's route
  // review found the rope lifted again, the board underfoot, water in a pool
  // marked 停水, 诺诺 moved 身后, and the goggles standing on their own.
  {
    for (const violation of settledStateViolations(text, inputText, priorText)) {
      issues.push(hard('self_contradiction', attempt, violation.detail, violation.sentence));
    }
    for (const violation of objectActorViolations(text, inputText)) {
      issues.push(hard('self_contradiction', attempt, violation.detail, violation.sentence));
    }
  }

  // The same elapsed time written twice in one passage (Chinese and Arabic) is
  // a reading defect the route batch showed: «三分钟过去…3分钟过去».
  {
    const duration = ledger.time?.duration;
    if (duration) {
      const CN = ['零', '一', '两', '三', '四', '五', '六', '七', '八', '九', '十'];
      const unit = ({ second: '秒', minute: '分钟', hour: '小时', day: '天', month: '个月', year: '年' } as Record<string, string>)[duration.unit] ?? '';
      const cn = Number.isInteger(duration.amount) && duration.amount >= 0 && duration.amount <= 10 ? CN[duration.amount] : null;
      if (unit && cn) {
        const chinese = text.includes(`${cn}${unit}`);
        const arabic = text.includes(`${duration.amount}${unit}`);
        if (chinese && arabic) {
          issues.push(hard('time_duplicate', attempt, `both 「${cn}${unit}」 and 「${duration.amount}${unit}」 are written`));
        }
      }
    }
  }

  // A scene prop (the wall board, the route map) is not carried. When the
  // passage puts one in a hand and the input never says it is held, that is a
  // new fact. 09 batch-5 wrote «演习规则牌在他手中，牌面写着…». Judged in
  // index.ts where the input text is available.
  // «他没看到任何人，也没听见任何声音» is the checklist form of a quiet turn,
  // and with someone in the scene it is also false. 09's accepted turns use it
  // as filler (95dc, dense point).
  {
    const ABSENT = /(没(?:有)?(?:看到|看见|见到)|空无一人|没有一个人|不见人影)/u;
    const present = (policy.scene?.present ?? []).map((person) => person.name).filter(Boolean);
    for (const sentence of sentences) {
      if (!ABSENT.test(sentence)) continue;
      const named = present.filter((name) => sentence.includes(name));
      if (present.length && !named.length) {
        issues.push(hard('self_contradiction', attempt,
          `text says nobody was seen while ${present.join('、')} is in the scene`, sentence));
      }
    }
  }

  // A passage that hears a sound and then says it heard no sound at all is
  // contradicting itself inside one paragraph. 09's accepted dense point
  // (real-qwen3-dense-point-4.json) has «听着远处传来轻微的水声» followed by
  // «也没有听到任何声音». This is not a fact check against the input: the two
  // clauses cannot both be true.
  {
    const HEARD = /(听见|听到|听着|传来|响起|响了一声|发出一声)/u;
    const NO_SOUND = /((?:没有|没)(?:听到|听见|听不到)|没有任何|没有一点)[^。！？]{0,6}(声音|动静)/u;
    const heardAt = sentences.findIndex((sentence) => HEARD.test(sentence) && !NO_SOUND.test(sentence));
    const silentAt = sentences.findIndex((sentence) => NO_SOUND.test(sentence));
    if (heardAt >= 0 && silentAt >= 0 && heardAt !== silentAt) {
      issues.push(hard('self_contradiction', attempt,
        'text hears a sound and also says it heard no sound at all', sentences[silentAt]));
    }
  }

  // The declared action may settle no state row (a read, a look). Its absence
  // is the «omitted player action» defect the product listed; there is no fact
  // to check against, so compare the action's own wording and note it softly.
  {
    const action = (policy.scene?.previousAction ?? '').trim();
    if (action.length >= 6) {
      const grams = new Set<string>();
      const cleaned = action.replace(/^我(?!们)/u, '').replace(/[。！？!?，,、；;：:\s]+/gu, '');
      for (let i = 0; i + 2 <= cleaned.length; i += 1) grams.add(cleaned.slice(i, i + 2));
      const body = text.replace(/[。！？!?，,、；;：:\s]+/gu, '');
      let shared = 0;
      for (const gram of grams) if (body.includes(gram)) shared += 1;
      if (grams.size && shared === 0) {
        issues.push(soft('unverified_sentence', attempt, 'the declared action is not written anywhere', undefined));
      }
    }
  }

  const minChars = policy.minChars ?? 60;
  if (chars > 0 && chars < Math.round(minChars * 0.67)) {
    issues.push(hard('too_short', attempt, `${chars} < ${Math.round(minChars * 0.67)} characters`));
  } else if (chars > 0 && chars < minChars) {
    issues.push(soft('shorter_than_contract', attempt, `${chars} < ${minChars} characters`));
  }
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

  // A verbatim sentence carried over from the previous passage is an echo even
  // when the whole-passage bigram overlap stays under the threshold: one reused
  // closing line in a short scene scores 0.34. The page showed the same closing
  // beat twice across turns; this is the sentence-level form of that defect.
  // maxPriorOverlap = 1 is the caller saying echo is allowed here (beat
  // assembly removes duplicates itself), so the sentence rule respects it.
  if (priorText && (policy.maxPriorOverlap ?? 0.55) < 1) {
    const normalizeSentence = (value: string) => value.replace(/[\s，。！？!?；;、]/gu, '');
    // Only the previous closing and opening lines are echoes: a state sentence
    // repeated in the middle («红发用发圈束在脑后») is the same true fact, and
    // 09's b7cd run was failed for exactly that on a later point.
    const priorParts = priorText.split(/[。！？!?\n]+/u).map(normalizeSentence).filter((entry) => entry.length >= 8);
    const priorSentences = new Set([priorParts[0], priorParts[priorParts.length - 1]].filter(Boolean) as string[]);
    for (const [index, sentence] of sentences.entries()) {
      const key = normalizeSentence(sentence);
      if (key.length < 8 || !priorSentences.has(key)) continue;
      // A repeated closing line has a deterministic fix in scene mode: the
      // accepted passage is trimmed by trimEchoedEnding. Rejecting the whole
      // draft for it cost 09 the model prose twice (d101, 415c) and paid for a
      // second generation. As the last sentence it is a soft note; anywhere
      // else the trimmer cannot remove it, so it stays hard.
      const last = index === sentences.length - 1;
      issues.push(last
        ? soft('echo_prior', attempt, 'last sentence repeats the previous closing line', sentence)
        : hard('echo_prior', attempt, 'sentence repeats the previous passage verbatim', sentence));
      break;
    }
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
  const clauses = text.split(CLAUSE_SPLIT).map(normalize).filter((entry) => entry.length >= 5);
  const clauseCount = new Map<string, number>();
  for (const entry of clauses) clauseCount.set(entry, (clauseCount.get(entry) ?? 0) + 1);
  // Twice is already an echo in a passage this short: the unseen-world run
  // wrote «三分钟过去» twice in 189 characters and nothing flagged it. The 71
  // reference scenes contain no clause of 8+ characters repeated even twice,
  // so the threshold is two, not three.
  const repeatedClauses = [...clauseCount.entries()].filter(([entry, count]) => count >= 2
    && !repeatedSentences.some(([sentence]) => sentence.includes(entry)));
  for (const [entry, count] of repeatedClauses) {
    // Two occurrences in a long page passage is a style flaw; three is a loop.
    // The page's trained candidate was rejected twice for a 2x clause and the
    // turn fell back to program text, which is a worse outcome than the echo.
    if (count >= 3) {
      issues.push(hard('loop_repeated_clause', attempt, `clause repeated ${count}x`, entry.slice(0, 80)));
    } else {
      issues.push(soft('loop_repeated_clause', attempt, `clause repeated ${count}x`, entry.slice(0, 80)));
    }
  }

  // Item-state changes the point did not settle. The upstream event list is
  // finite and misses synonyms a small model actually uses ("开启" for
  // "打开"), so an object name next to an open/take/put verb is checked
  // separately. `policy.scene.objects` is the caller's visible-object list;
  // `licensedEvents` is the player's committed action, not a model guess.
  const itemNames = [...new Set([
    ...(policy.scene?.objects ?? []).map((object) => object.name),
    ...(policy.visibleEntities ?? []),
  ])].filter((name) => name.length >= 2);
  if (itemNames.length) {
    // Plot-changing item verbs. Micro-actions on a visible prop (合上/拿起/
    // 放下/推到/翻开) are allowed: the corpus uses them to make a scene
    // concrete. The upstream added_event check still catches an unlicensed
    // 递给; this local guard is for opening/consuming/creating an item.
    const ITEM_STATE = /(打开|开启|掀开|揭开|锁上|拿出|取出|抽出|放进|塞进|摔碎|撕开|点燃|熄灭|吃掉|喝掉)/u;
    const CLAUSE = CLAUSE_SPLIT;
    for (const sentence of sentences) {
      for (const clause of sentence.split(CLAUSE)) {
        const verb = ITEM_STATE.exec(clause)?.[1];
        if (!verb || ledger.allowedEvents.includes(verb)) continue;
        const item = itemNames.find((name) => clause.includes(name));
        if (item) {
          issues.push(hard('fact_event_added', attempt, `item ${item} changes state (${verb}) with no committed fact`, sentence));
          break;
        }
      }
    }
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
    if (!text.includes(name)) continue;
    // A distant landmark is background, not an event: the page's own roster
    // carries places the scene input does not spell out, and failing a scene
    // for naming 钟楼 while standing in the alley is a false rejection.
    // A visible object of the scene is background too: the projector put it in
    // front of the viewpoint, so naming it cannot be a new world fact even when
    // the serialized text does not spell out where it lies. 09's 21c3 turn was
    // rejected for «诺诺的红色识别带», an item worn by a present character.
    const sceneNames = (policy.scene?.objects ?? []).map((object) => object.name);
    if (sceneNames.includes(name)) {
      issues.push(soft('unverified_sentence', attempt, `visible object ${name} named in passing`, undefined));
      continue;
    }
    if ((policy.locations ?? []).includes(name)) {
      issues.push(soft('unverified_sentence', attempt, `distant place ${name} named in passing`, undefined));
      continue;
    }
    issues.push(hard('unlicensed_entity', attempt, `${name} is in no committed fact or licensed context`));
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
