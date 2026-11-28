/** Read-only structured events derived from settled result facts and the
 * committed state delta. This is a compatibility view: it never mutates
 * WorldState and can always be rebuilt from the facts. */
import type { Id, WorldState } from '../../types';

export type EventResult = 'completed' | 'partial' | 'failed' | 'blocked' | 'unaffected';
export type EvidenceState = 'present' | 'absent' | 'insufficient' | 'conflict';

export interface StructuredEvent {
  id: string;
  actorId: Id;
  targetIds: Id[];
  action: string;
  objectIds: Id[];
  result: EventResult;
  degree: string | null;
  cause: string | null;
  location: Id | null;
  info: { entityId: Id; text: string } | null;
  envChanges: Array<{ entityId: Id; text: string }>;
  relations: Array<{ kind: string; eventId: string }>;
  source: { factId: string; turn: number | null; text: string };
  evidence: EvidenceState;
}

export interface ResultFactInput {
  id: string;
  memberId: Id;
  text: string;
}

const OUTCOME: Array<[RegExp, EventResult, string | null]> = [
  [/（达到目的）/u, 'completed', null],
  [/（只完成一部分）/u, 'partial', '只完成一部分'],
  [/（没有成功）/u, 'failed', null],
  [/（被阻止）/u, 'blocked', null],
  [/（没有变化）/u, 'unaffected', null],
];

function nameOf(state: WorldState, id: Id): string {
  return state.initial.locations[id]?.name ?? state.initial.items[id]?.name
    ?? state.initial.characters[id]?.name ?? id;
}

function registered(state: WorldState, id: string): boolean {
  return Boolean(state.initial.locations[id] || state.initial.items[id] || state.initial.characters[id]);
}

function cleanText(text: string): string {
  return text
    .replace(/（达到目的）|（只完成一部分）|（没有成功）|（被阻止）|（没有变化）/gu, '')
    .replace(/；?(?:去向|环境|信息|涉及)=[^；。]*/gu, '')
    .trim();
}

export function buildStructuredEvents(input: {
  facts: ResultFactInput[];
  before: WorldState;
  after: WorldState;
  turn?: number | null;
}): StructuredEvent[] {
  const events: StructuredEvent[] = [];
  for (const fact of input.facts) {
    const text = fact.text;
    const outcome = OUTCOME.find(([pattern]) => pattern.test(text));
    const result: EventResult = outcome?.[1] ?? 'unaffected';
    const envChanges = [...text.matchAll(/环境=([^:；]+):([^；。]*)/gu)]
      .filter((match) => registered(input.after, match[1]))
      .map((match) => ({ entityId: match[1], text: match[2] }));
    const infoMatch = /信息=([^:；]+):([^；。]*)/u.exec(text);
    const info = infoMatch && registered(input.after, infoMatch[1]) ? { entityId: infoMatch[1], text: infoMatch[2] } : null;
    const destination = /去向=[^:；]+:([^/；。]+)/u.exec(text);
    const location = destination && registered(input.after, destination[1]) ? destination[1] : null;
    const involved = /涉及=([^；。]+)/u.exec(text);
    const targetIds = involved
      ? involved[1].split(/[,，、]/u).map((id) => id.trim()).filter((id) => Boolean(input.after.characters[id]))
      : Object.entries(input.after.initial.characters)
        .filter(([id, character]) => id !== fact.memberId && character.name && text.includes(character.name))
        .map(([id]) => id);
    const objectIds: Id[] = [];
    if (destination) {
      const item = /去向=([^:；]+):/u.exec(text)?.[1];
      if (item && input.after.initial.items[item]) objectIds.push(item);
    }
    const actorAfter = input.after.characters[fact.memberId]?.position?.containerId ?? null;
    let evidence: EvidenceState = outcome ? 'present' : 'insufficient';
    if (result === 'failed' || result === 'blocked') evidence = 'absent';
    if (result === 'completed' && location && actorAfter && actorAfter !== location) evidence = 'conflict';
    const action = cleanText(text).replace(new RegExp(`^${input.after.initial.characters[fact.memberId]?.name ?? fact.memberId}`, 'u'), '').trim();
    events.push({
      id: `evt_${fact.id}`,
      actorId: fact.memberId,
      targetIds,
      action: action || nameOf(input.after, fact.memberId),
      objectIds,
      result,
      degree: outcome?.[2] ?? null,
      cause: null,
      location,
      info,
      envChanges,
      relations: [],
      source: { factId: fact.id, turn: input.turn ?? null, text },
      evidence,
    });
  }
  return events;
}
