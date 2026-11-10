/** What a committed point contributes to prose.
 *
 * The shared packet carries two different kinds of truth:
 *  - things that happened (a move, a task reached): prose must state them;
 *  - standing state (where everyone is, a stat value, a personality line):
 *    prose must not recite these as a ledger.
 *
 * Qwen-1.5B in the first real probe wrote “精神值为10” because the reference
 * prompt listed every sanity fact. That is not a model defect; it is the
 * prompt treating state as events. Here the packet is split: movement/task
 * facts stay required, positions become known scene standing, and stats or
 * personality changes become behaviour hints with no numbers and no quotes.
 * Verification runs on the same projection, so a passage is never failed for
 * not reciting a number it was told not to say.
 */
import type { CommittedNarration, NarrationFact } from '../../../runtime/committed-narration';
import type { CandidatePolicy } from './types';

export interface ProseProjection {
  /** Facts the passage must express. */
  packet: CommittedNarration;
  /** Positions that are already true; stating them is not a new event. */
  positions: { name: string; location: string }[];
  /** Internal changes, to be shown through behaviour. Never quoted. */
  hints: string[];
  /** Facts left out of the required set, kept for evidence. */
  withheld: NarrationFact[];
}

const REQUIRED: ReadonlySet<NarrationFact['kind']> = new Set(['moved', 'task_achieved']);

export function projectProseFacts(committed: CommittedNarration): ProseProjection {
  const facts: NarrationFact[] = [];
  const positions: { name: string; location: string }[] = [];
  const hints: string[] = [];
  const withheld: NarrationFact[] = [];
  for (const fact of committed.facts) {
    if (REQUIRED.has(fact.kind)) {
      facts.push(fact);
      continue;
    }
    withheld.push(fact);
    if (fact.kind === 'at') {
      positions.push({ name: fact.name, location: fact.location });
    } else if (fact.kind === 'sanity_changed') {
      hints.push(`${fact.name}的心神有了波动（只用动作或神态表现，不要写出任何数值）`);
    } else if (fact.kind === 'personality_changed') {
      hints.push(`${fact.name}的性情发生了变化：${fact.text}。用行为表现它，不要照抄这句话`);
    }
  }
  return { packet: { ...committed, facts }, positions, hints, withheld };
}

/** Caller-supplied positions first, then the packet's standing positions.
 * A name appears once; the caller's wording wins. */
export function mergePositions(
  policy: CandidatePolicy['knownPositions'],
  projected: { name: string; location: string }[],
): { name: string; location: string }[] {
  const out: { name: string; location: string }[] = [];
  const seen = new Set<string>();
  for (const entry of [...(policy ?? []), ...projected]) {
    if (seen.has(entry.name)) continue;
    seen.add(entry.name);
    out.push(entry);
  }
  return out;
}
