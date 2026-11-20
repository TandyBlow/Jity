/** Read-only fact license ledger.
 *
 * The ledger answers three questions before a single token is generated:
 * which settled changes MUST appear in the prose, which names the scene is
 * allowed to use, and which event verbs the player's committed action already
 * licensed. It never mutates the packet and never creates a second source of
 * truth: every entry is copied from the committed facts, the caller's
 * serialized input, the previous accepted narration, or explicit policy names.
 */
import type { CommittedNarration, NarrationFact } from '../../runtime/committed-narration';
import type { NarrationLedger, NarrationPolicy } from './types';

/** A change the reader must be able to see. Static `at`/`sanity` facts are the
 * scene's backdrop, not this point's result, so they stay optional: requiring
 * them would turn every scene into a roll-call. */
const MANDATORY_KINDS: ReadonlySet<NarrationFact['kind']> = new Set<NarrationFact['kind']>([
  'moved', 'task_achieved', 'personality_changed', 'sanity_changed',
]);

const unique = (values: readonly string[]): string[] => [...new Set(values.filter((value) => value.length > 0))];

/** Continuity checks need a source: a promise or a past reference is licensed
 * when the same marker is already in the serialized input, the previous
 * accepted prose, or the caller's explicit event license. */
export const PROMISE_VERBS = ['答应', '承诺', '保证', '发誓', '许诺', '约好', '说好'];
export const PAST_MARKERS = ['小时候', '童年', '儿时', '当年', '十年前', '从前', '曾经', '很久以前', '那一年'];

export function buildLedger(
  committed: CommittedNarration,
  inputText: string,
  policy: NarrationPolicy,
): NarrationLedger {
  const facts = committed.facts;
  const mandatory = facts.filter((fact) => MANDATORY_KINDS.has(fact.kind));
  const optional = facts.filter((fact) => !MANDATORY_KINDS.has(fact.kind));
  const actorNames = unique(facts.map((fact) => fact.name));
  const locationNames = unique(facts.flatMap((fact) => {
    if (fact.kind === 'at') return [fact.location];
    if (fact.kind === 'moved') return [fact.from, fact.to];
    return [];
  }));
  const viewpoint = policy.viewpoint?.name
    ? { id: policy.viewpoint.id ?? null, name: policy.viewpoint.name }
    : null;
  // Licensed names: everything the fact packet names, everything the caller's
  // serialization contains (the serialized input is the authority on what this
  // scene may mention), explicit visible entities, and names already used by
  // the previous accepted narration (legal prior text).
  const licensed = new Set<string>([
    ...actorNames,
    ...locationNames,
    ...(policy.visibleEntities ?? []),
    ...(viewpoint ? [viewpoint.name] : []),
  ]);
  for (const name of policy.knownEntities ?? []) {
    if (name.length < 2) continue;
    if (inputText.includes(name)) licensed.add(name);
  }
  const factText = facts.flatMap((fact) => fact.kind === 'personality_changed' ? [fact.text] : []).join('\n');
  const sourceText = [inputText, factText].join(String.fromCharCode(10));
  const licensedPromises = PROMISE_VERBS.filter((verb) => sourceText.includes(verb) || (policy.licensedEvents ?? []).includes(verb));
  const licensedPastMarkers = PAST_MARKERS.filter((marker) => sourceText.includes(marker));
  const time = policy.time ?? null;
  const requireTime = policy.requireTime
    ?? (time !== null && time.boundary === 'elapsed' && time.duration.amount > 0);
  return {
    viewpoint,
    mandatory,
    optional,
    actorNames,
    locationNames,
    licensedEntities: [...licensed],
    allowedEvents: unique(policy.licensedEvents ?? []),
    licensedPromises,
    licensedPastMarkers,
    time,
    requireTime,
    forbiddenKnowledge: unique(policy.forbiddenKnowledge ?? []),
  };
}
