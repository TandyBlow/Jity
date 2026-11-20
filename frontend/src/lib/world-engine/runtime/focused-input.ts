/** Explicit, opt-in input views for the supported command subset. They
 * reduce duplicated initial/live state, not the execution authority checks.
 * Other tasks/stages retain their full input rather than silently losing data. */
import type { Json, WorldState } from '../types';
import type { ModelTask } from '../schedule';
import { projectCommittedNarration, factPhrases, type CommittedRead } from './committed-narration';

const json = (value: unknown): Json => JSON.parse(JSON.stringify(value)) as Json;
const activeText = (changes: { text: string | null; active: boolean }[]) => changes.filter((change) => change.active && change.text !== null).map((change) => change.text);
function placeOf(state: WorldState, id: string): string {
  const seen = new Set<string>();
  while (!state.locations[id]) {
    if (seen.has(id)) throw new Error('focused_position_cycle');
    seen.add(id);
    const entity = state.characters[id] ?? state.items[id];
    if (!entity) throw new Error('focused_position_unresolved');
    id = entity.position.containerId;
  }
  return id;
}

export function projectTaskInput(task: ModelTask, input: Json, committedReads?: { before: CommittedRead | null; after: CommittedRead }): Json {
  const data = input as unknown as { actor?: string; advance?: unknown; workingState?: WorldState;
    stage?: string; groupId?: string; results?: unknown; ruleAssessment?: unknown; pointId?: string;
    before?: WorldState | null; after?: WorldState; delta?: unknown };
  if (task === 'action' && data?.workingState && data.actor) {
    const state = data.workingState;
    const actor = state.characters[data.actor];
    const original = state.initial.characters[data.actor];
    if (!actor || !original) throw new Error('focused_actor_missing');
    const place = placeOf(state, data.actor);
    return json({ actor: data.actor, protagonistId: state.protagonistId, advance: data.advance, currentTime: state.time,
      actorState: { id: data.actor, name: original.name, position: actor.position, sanity: actor.sanity,
        personality: { initial: original.initialPersonality, active: activeText(actor.personalityChanges) },
        tasks: Object.values(actor.tasks).map(({ id, goal, status }) => ({ id, goal, status })) },
      locations: Object.entries(state.initial.locations).map(([id, location]) => ({ id, name: location.name,
        parentLocationId: location.parentLocationId, appearance: { initial: location.initialAppearance, active: activeText(state.locations[id].appearanceChanges) } })),
      nearbyCharacters: Object.entries(state.characters).filter(([id]) => id !== data.actor && placeOf(state, id) === place)
        .map(([id, character]) => ({ id, name: state.initial.characters[id].name, position: character.position })),
      nearbyItems: Object.entries(state.items).filter(([id]) => placeOf(state, id) === place)
        .map(([id, item]) => ({ id, name: state.initial.items[id].name, position: item.position,
          appearance: { initial: state.initial.items[id].initialAppearance, active: activeText(item.appearanceChanges) } })),
      meaning: 'action proposal only; execution must be adjudicated by program rules',
    });
  }
  if (task === 'updates' && data?.workingState && (data.stage === 'position' || data.stage === 'sanity')) {
    const state = data.workingState;
    return json({ groupId: data.groupId, stage: data.stage,
      entities: Object.entries(state.characters).map(([id, actor]) => ({ id, name: state.initial.characters[id].name,
        ...(data.stage === 'position' ? { position: actor.position } : { sanity: actor.sanity }) })),
      ...(data.stage === 'position' ? { locations: Object.entries(state.initial.locations).map(([id, location]) => ({ id, name: location.name })) } : {}),
      resultDescription: data.results, ruleAssessmentForComparison: data.ruleAssessment,
      meaning: 'comparison candidate only; natural-language results do not mint a rule receipt',
    });
  }
  if (task === 'narration' && committedReads) {
    if (data.pointId !== committedReads.after.pointId || JSON.stringify(data.before) !== JSON.stringify(committedReads.before?.state ?? null)
      || JSON.stringify(data.after) !== JSON.stringify(committedReads.after.state)
      || JSON.stringify(data.delta) !== JSON.stringify({ timeAdvance: committedReads.after.timeAdvance, entityDeltas: committedReads.after.entityDeltas })) throw new Error('focused_narration_read_binding_mismatch');
    const packet = projectCommittedNarration(committedReads.after, committedReads.before);
    return json({ pointId: packet.anchor.pointId,
      meaning: 'only express these saved facts; no additional people, locations, numbers or events',
      facts: packet.facts.map((fact) => ({ id: fact.id, allowedPhrases: factPhrases(fact) })) });
  }
  return input;
}
