/** The narrow committed-fact projection the page already uses.
 *
 * The page's `LocalGameModel` derives the alignment packet from
 * `before/delta/after` (characters only: position, sanity, task, personality,
 * plus the protagonist's standing room). This module exposes the same
 * derivation so a candidate caller that has the settled point but no packet —
 * the browser runner, lane 09's driver, lane 06's adapter — grades against the
 * same facts instead of inventing a weaker or different set. It is derived
 * data, not a second state store.
 */
import type { CommittedNarration, NarrationFact } from '../../../runtime/committed-narration';
import type { Id, WorldState } from '../../../types';
import { locationName } from '../../prompt';
import type { CandidateDelta } from './types';

export function projectFacts(
  before: WorldState | null,
  delta: CandidateDelta | null,
  after: WorldState,
  viewId: Id = after.protagonistId,
): CommittedNarration {
  const facts: NarrationFact[] = [];
  const changed = Object.keys(delta?.entityDeltas ?? {});
  const ids = new Set<Id>([viewId, ...changed]);
  for (const id of ids) {
    const character = after.characters[id];
    const name = after.initial.characters[id]?.name;
    if (!character || !name) continue;
    const previous = before?.characters[id];
    const entityDelta = delta?.entityDeltas?.[id];
    if (entityDelta?.positionSet) {
      const fromId = previous?.position.containerId;
      const from = fromId ? before?.initial.locations[fromId]?.name : undefined;
      if (from && fromId) {
        facts.push({
          id: `${id}:position`, actorId: id, name, kind: 'moved',
          fromId, from, toId: character.position.containerId, to: locationName(after, character.position.containerId),
        });
      }
    } else if (id === viewId) {
      facts.push({
        id: `${id}:position`, actorId: id, name, kind: 'at',
        locationId: character.position.containerId, location: locationName(after, character.position.containerId),
      });
    }
    if (entityDelta?.sanitySet != null && previous) {
      facts.push({ id: `${id}:sanity`, actorId: id, name, kind: 'sanity_changed', from: previous.sanity, to: character.sanity });
    }
    for (const taskId of entityDelta?.tasksAchieved ?? []) {
      const task = character.tasks[taskId];
      if (task) facts.push({ id: `${id}:task:${taskId}`, actorId: id, name, kind: 'task_achieved', taskId, goal: task.goal });
    }
    for (const change of entityDelta?.personalityChanges ?? []) {
      if (change.text) facts.push({ id: `${id}:personality:${change.id}`, actorId: id, name, kind: 'personality_changed', changeId: change.id, text: change.text });
    }
  }
  return {
    anchor: {
      worldId: after.worldId, pointId: 'candidate_point', version: 0,
      stateDigest: '', previousPointId: null,
    },
    facts,
  };
}
