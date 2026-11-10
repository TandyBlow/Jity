/** Verification of one draft against the committed point.
 *
 * The fact core reuses `runtime/narration-alignment`, the same grader the page
 * uses, so a candidate cannot invent a weaker standard. On top of it this
 * module checks the things the projection (not the fact packet) knows:
 * unlicensed character names, item destinations, time, length, continuity and
 * a leaked reasoning trace. `added_event` is downgraded only when the exact
 * verb is licensed by the player's own committed action or a settled result
 * line; everything else stays a hard failure.
 */
import type { CommittedNarration } from '../../../runtime/committed-narration';
import { factPhrases } from '../../../runtime/committed-narration';
import { alignNarration, repetitionAgainst } from '../../../runtime/narration-alignment';
import type { CandidateIssue, InstructCandidatePolicy, SceneProjection } from './types';

const SENTENCE_SPLIT = /(?<=[。！？!?])|\n+/;

export function sentencesOf(text: string): string[] {
  return text.split(SENTENCE_SPLIT).map((part) => part.trim()).filter(Boolean);
}

const STOP_CHARS = new Set('的了着把被在与和或到为是能会要就才也都又再很太更最地得之其这那个一'.split(''));

/** Content bigrams of a task goal: `把故障短讯机恢复到能与凯撒联络的状态`
 * yields 故障/短讯/讯机/恢复/凯撒/联络/状态 plus bridging pairs. Two of them in
 * the same sentence as the actor is the weakest reading that still tells the
 * player the task happened; it cannot be satisfied by "她看起来很高兴". */
function contentBigrams(goal: string): string[] {
  const chars = [...goal.replace(/[「」『』，。、；：！？\s]/g, '')];
  const grams: string[] = [];
  for (let index = 0; index + 1 < chars.length; index++) {
    const pair = chars[index] + chars[index + 1];
    if (STOP_CHARS.has(chars[index]) || STOP_CHARS.has(chars[index + 1])) continue;
    if (!grams.includes(pair)) grams.push(pair);
  }
  return grams;
}

export function taskStated(text: string, actor: string, goal: string): boolean {
  if (!goal) return true;
  if (text.includes(goal)) return true;
  const grams = contentBigrams(goal);
  if (!grams.length) return true;
  return sentencesOf(text).some((sentence) => sentence.includes(actor)
    && grams.filter((gram) => sentence.includes(gram)).length >= 2);
}

function unquoted(text: string): string {
  return text
    .replace(/“[^”]*”/g, '“”')
    .replace(/"[^"]*"/g, '""')
    .replace(/「[^」]*」/g, '「」')
    .replace(/『[^』]*』/g, '『』')
    .replace(/‘[^’]*’/g, '‘’');
}

export interface VerifyInputs {
  text: string;
  projection: SceneProjection;
  committed: CommittedNarration | null;
  policy: InstructCandidatePolicy;
  previousText?: string | null;
  licensedText: string[];
}

export interface VerifyResult {
  issues: CandidateIssue[];
  accepted: boolean;
  /** Committed facts the prose did not express (ids). */
  omissions: string[];
  unverifiedSentences: number;
}

function issue(kind: CandidateIssue['kind'], severity: 'hard' | 'soft', detail: string, sentence?: string): CandidateIssue {
  return { kind, severity, attempt: 0, detail, sentence };
}

export function verifyDraft(inputs: VerifyInputs): VerifyResult {
  const { text, projection, committed, policy } = inputs;
  const issues: CandidateIssue[] = [];
  const chars = [...text].length;
  const minChars = policy.minChars ?? 90;
  const maxChars = policy.maxChars ?? Math.max(520, (policy.targetChars ?? 260) * 2);
  if (chars < minChars) issues.push(issue('too_short', 'hard', `${chars} chars < ${minChars}`));
  if (chars > maxChars) issues.push(issue('too_long', 'soft', `${chars} chars > ${maxChars}`));

  // Unlicensed character names: a name from another room appearing here is a
  // pretraining pull, exactly the failure mode the runtime validates against.
  const licensedNames = new Set([
    ...projection.characters.map((entry) => entry.name),
    ...(policy.visibleEntities ?? []),
    ...projection.items.map((item) => item.name),
    projection.place.name,
    ...projection.positions.map((entry) => entry.location),
    // A movement fact legitimately names its origin and destination.
    ...projection.facts.flatMap((fact) => [fact.from, fact.to]).filter((name): name is string => Boolean(name)),
  ]);
  const licensedText = inputs.licensedText.join('\n');
  for (const name of projection.licensing.roster) {
    if (!name || name.length < 2 || licensedNames.has(name)) continue;
    if (licensedText.includes(name)) continue;
    if (text.includes(name)) issues.push(issue('unlicensed_entity', 'hard', `${name} is not in this scene`, name));
  }
  for (const name of [...projection.licensing.items, ...projection.licensing.locations]) {
    if (!name || name.length < 2 || licensedNames.has(name)) continue;
    if (licensedText.includes(name)) continue;
    if (text.includes(name)) issues.push(issue('unlicensed_entity', 'hard', `${name} is not visible in this scene`, name));
  }
  for (const secret of projection.licensing.forbiddenKnowledge) {
    if (secret && text.includes(secret)) issues.push(issue('unlicensed_entity', 'hard', 'forbidden knowledge leaked', secret));
  }

  // Third-person narration. An occasional unquoted “我” inside the
  // protagonist's thought is legitimate; a draft that starts with 我 and never
  // names anyone is a first-person narrator.
  const narration = unquoted(text);
  const firstPerson = (narration.match(/我/g) ?? []).length;
  const namesAnyone = projection.characters.some((entry) => entry.name.length >= 2 && text.includes(entry.name));
  if (firstPerson > 0 && (!namesAnyone || (/^\s*我/.test(text) && firstPerson >= 2))) {
    issues.push(issue('first_person_narrator', 'hard', `first person outside dialogue (${firstPerson})`));
  }

  if (committed && committed.facts.length) {
    const time = projection.advance && projection.advance.duration.amount > 0
      ? { amount: projection.advance.duration.amount, unit: projection.advance.duration.unit }
      : null;
    const alignment = alignNarration(committed, text, {
      roster: projection.licensing.roster,
      locations: projection.licensing.locations,
      knownPositions: projection.licensing.knownPositions,
      time,
      requireTime: time !== null && (policy.requireTime ?? true),
      previousText: inputs.previousText ?? null,
    });
    const licensedEvents = new Set([
      ...projection.licensing.licensedEvents,
      ...(policy.licensedEvents ?? []),
    ]);
    for (const verb of licensedEvents) licensedEvents.add(verb);
    for (const violation of alignment.violations) {
      if (violation.kind === 'empty_narration') continue; // shape handles it
      if (violation.kind === 'movement_without_fact') {
        // A pronoun movement toward the place the player's own committed
        // action already walked to is not a fabricated move. The grader is
        // name-based and cannot bind 「他朝器材棚走去」; the player action can.
        const location = projection.licensing.locations.find((name) => violation.sentence.includes(name));
        if (location && licensedText.includes(location)) {
          issues.push(issue('licensed_event', 'soft', `movement toward ${location} licensed by the player action`, violation.sentence));
          continue;
        }
      }
      if (violation.kind === 'added_event') {
        const match = violation.detail.match(/event verb (\S+) has no committed fact/);
        const verb = match?.[1];
        if (verb && (licensedEvents.has(verb) || licensedText.includes(verb))) {
          issues.push(issue('licensed_event', 'soft', `${verb} licensed by the player action/result`, violation.sentence));
          continue;
        }
      }
      issues.push(issue(violation.kind, 'hard', violation.detail, violation.sentence));
    }
    // Omissions: visible changes are hard; stat/trait changes are soft. The
    // runtime grader binds a task only to its frozen goal string and a sanity
    // change only to its exact numbers, which cannot coexist with novel prose.
    // A task still has to be *said* — the actor plus at least two content
    // bigrams of the goal in one sentence — so the reader learns it happened.
    const expressed = new Set(alignment.coverage.filter((entry) => entry.expressed).map((entry) => entry.id));
    // 「两人一起走进庭院」 is a legitimate rendering of two per-actor move
    // facts: the grader can only bind names, so the group phrasing is credited
    // to every actor that shares the same origin and destination.
    const groupMove = (fact: { name: string; from: string; to: string }): boolean => {
      const peers = committed.facts.filter((entry) => entry.kind === 'moved'
        && entry.from === fact.from && entry.to === fact.to);
      if (peers.length < 2) return false;
      const actorNames = peers.map((entry) => entry.name).filter((name) => text.includes(name));
      if (actorNames.length === peers.length) return true; // names are there; binding may still fail
      return /两人|二人|他们|她们|一行人/.test(text) && text.includes(fact.to)
        && new RegExp('(?:走到|走进|来到|进入|赶到|前往|抵达|走向|朝)').test(text);
    };
    for (const fact of committed.facts) {
      if (expressed.has(fact.id)) continue;
      const label = factPhrases(fact)[0];
      if (fact.kind === 'moved' && groupMove(fact as typeof fact & { from: string; to: string })) {
        issues.push(issue('fact_omitted', 'soft', `${label} (group phrasing)`));
        continue;
      }
      if (fact.kind === 'task_achieved') {
        if (!taskStated(text, fact.name, fact.goal)) issues.push(issue('fact_omitted', 'hard', label));
        else issues.push(issue('fact_omitted', 'soft', `${label} (stated without the frozen goal wording)`));
        continue;
      }
      if (fact.kind === 'sanity' || fact.kind === 'sanity_changed' || fact.kind === 'personality_changed' || fact.kind === 'at') {
        // A standing position is not a change, and a stat/trait change is not
        // always something a scene would say. They stay soft; contradictions
        // are still hard (the alignment violations above).
        issues.push(issue('fact_omitted', 'soft', `${label} (not stated)`));
        continue;
      }
      issues.push(issue('fact_omitted', 'hard', label));
    }
    if (time && (policy.requireTime ?? true) && alignment.timeExpressed === false) {
      issues.push(issue('time_missing', 'hard', `time advance ${time.amount} ${time.unit} not narrated`));
    }
    for (const fact of inputs.projection.facts.filter((entry) => entry.kind === 'item_moved')) {
      if (fact.entity && !text.includes(fact.entity)) {
        issues.push(issue('fact_omitted', 'hard', `item change not narrated: ${fact.statement}`));
      } else if (fact.holder && !sentencesOf(text).some((sentence) => sentence.includes(fact.holder!) && (fact.entity ? sentence.includes(fact.entity) : true))) {
        issues.push(issue('fact_omitted', 'soft', `item change does not say it reached ${fact.holder}: ${fact.statement}`));
      }
    }
    // Small-model loop: the same 8-char clause three times is not prose.
    const shingles = new Map<string, number>();
    for (const sentence of sentencesOf(text)) {
      for (let index = 0; index + 8 <= sentence.length; index += 4) {
        const shingle = sentence.slice(index, index + 8);
        shingles.set(shingle, (shingles.get(shingle) ?? 0) + 1);
      }
    }
    const looped = [...shingles.entries()].find(([, count]) => count >= 3);
    if (looped) issues.push(issue('loop_repeated', 'hard', `clause repeated: ${looped[0]} x${looped[1]}`));
    const unverified = alignment.unverified.length;
    const repetition = repetitionAgainst(text, inputs.previousText ?? null);
    if (repetition !== null) {
      if (repetition > 0.6) issues.push(issue('echo_prior', 'hard', `bigram overlap ${(repetition * 100).toFixed(0)}% with prior text`));
      else if (repetition > 0.4) issues.push(issue('echo_prior', 'soft', `bigram overlap ${(repetition * 100).toFixed(0)}% with prior text`));
    }
    return { issues, accepted: !issues.some((entry) => entry.severity === 'hard'), omissions: alignment.omissions, unverifiedSentences: unverified };
  }

  // No committed packet: facts cannot be graded, so the draft cannot be
  // accepted. Say so instead of pretending the text passed.
  issues.push(issue('facts_unverified', 'hard', 'no committed packet was supplied; draft is not fact-graded'));
  return { issues, accepted: !issues.some((entry) => entry.severity === 'hard'), omissions: [], unverifiedSentences: 0 };
}
