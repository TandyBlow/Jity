/** Read-only projection of one settled point into candidate-ready material.
 *
 * Three outputs come from the SAME sealed records (`before`, the point's
 * `delta`, `after`):
 *
 *   - `facts`: the committed narration vocabulary (moved / at / sanity /
 *     task / personality). Candidates use it as the fact license.
 *   - `inputText`: lane 01's `yuyan-prose-result-v2` serializer. This module
 *     never re-serializes state by hand; if the projection refuses the point,
 *     the input is reported missing instead of being patched up.
 *   - `policy`/`scene`: names, rooms, visible objects and length/temperature
 *     limits. They license material; they cannot add a fact.
 *
 * The projector deliberately does not call `projectCommittedNarration`: that
 * gate requires the `get_state` lineage (digests/versions) the narration call
 * does not receive, and it rejects slot positions, which the product world
 * uses. Facts here are copied from the sealed delta and the settled states
 * only; no change is inferred from prose.
 */
import type { EntityDelta, Id, Position, TimeAdvance, WorldState } from '../../../types';
import type { CommittedNarration, NarrationFact } from '../../../runtime/committed-narration';
import { EVENT_VERBS } from '../../../runtime/narration-alignment';
import type { BeatSceneContext, NarrationPolicy } from '../../narration-generation/types';
import { projectNarrationInput } from '../../narration-input';
import { renderResultInput } from '../../narration-input';
import type { NarrationPoint, PreparedNarration } from './types';

const INSTANT: TimeAdvance = { boundary: 'instant', duration: { amount: 0, unit: 'second' } };

/** Facts B's ledger treats as mandatory (`MANDATORY_KINDS`). Kept here only
 * for the evidence summary; the candidate owns its own requirement list. */
const MANDATORY = new Set(['moved', 'task_achieved', 'personality_changed', 'sanity_changed']);

type AnyPositioned = { position: Position };

function positionOf(state: WorldState, entityId: Id): AnyPositioned | null {
  return state.characters[entityId] ?? state.items[entityId] ?? null;
}

function nameOf(state: WorldState, entityId: Id): string {
  return state.initial.locations[entityId]?.name
    ?? state.initial.items[entityId]?.name
    ?? state.initial.characters[entityId]?.name
    ?? entityId;
}

/** Innermost location of an entity: follow the container chain (chair → room)
 * until a registered location. Returns null for an unplaced entity. */
function roomOf(state: WorldState, entityId: Id): Id | null {
  const start = positionOf(state, entityId);
  if (!start) return null;
  const seen = new Set<Id>([entityId]);
  let node = start.position.containerId;
  for (let depth = 0; depth < 16; depth += 1) {
    if (seen.has(node)) return null;
    seen.add(node);
    if (state.initial.locations[node]) return node;
    const next = positionOf(state, node);
    if (!next) return null;
    node = next.position.containerId;
  }
  return null;
}

function visibleRoomOf(state: WorldState, entityId: Id): Id | null {
  return roomOf(state, entityId);
}

function activeNotes(state: WorldState, entityId: Id, initial: string): string[] {
  const stored = state.locations[entityId]?.appearanceChanges
    ?? state.items[entityId]?.appearanceChanges
    ?? state.characters[entityId]?.appearanceChanges
    ?? [];
  return [
    initial,
    ...stored.filter((change) => change.active && change.text).map((change) => change.text as string),
  ].filter((line): line is string => Boolean(line && line.trim()));
}

function changes(state: WorldState, entityId: Id): { id: Id; text: string | null; active: boolean }[] {
  return state.characters[entityId]?.personalityChanges ?? [];
}

/** Fact packet for the candidates. `anchor` carries the point identity we do
 * have; digest fields are copied from the caller when it supplies them and are
 * otherwise empty strings (the candidates never read them). */
export function projectNarrationFacts(point: NarrationPoint): CommittedNarration {
  const { before, after } = point;
  const facts: NarrationFact[] = [];
  const seen = new Set<string>();
  const push = (fact: NarrationFact): void => {
    if (seen.has(fact.id)) return;
    seen.add(fact.id);
    facts.push(fact);
  };
  const view = after.protagonistId;
  const deltas = point.delta.entityDeltas ?? {};

  const roomBefore = (entityId: Id): Id | null => (before ? roomOf(before, entityId) : null);
  const roomAfter = (entityId: Id): Id | null => roomOf(after, entityId);

  /** Placement + movement for characters and items. Only a room-to-room change
   * is a `moved` fact; a slot change inside one room stays scene detail. */
  const projectPosition = (entityId: Id, name: string, delta: EntityDelta | undefined): void => {
    const fromRoom = roomBefore(entityId);
    const toRoom = roomAfter(entityId);
    if (delta?.positionSet !== undefined && fromRoom && toRoom && fromRoom !== toRoom) {
      push({
        id: `${entityId}:position`, actorId: entityId, name, kind: 'moved',
        fromId: fromRoom, from: nameOf(before ?? after, fromRoom), toId: toRoom, to: nameOf(after, toRoom),
      });
      return;
    }
    if (toRoom) {
      push({ id: `${entityId}:position`, actorId: entityId, name, kind: 'at', locationId: toRoom, location: nameOf(after, toRoom) });
    }
  };

  for (const [entityId, delta] of Object.entries(deltas)) {
    const isCharacter = Boolean(after.characters[entityId]);
    const name = after.initial.characters[entityId]?.name ?? after.initial.items[entityId]?.name;
    if (!name) continue;
    projectPosition(entityId, name, delta);
    if (isCharacter) {
      const previous = before?.characters[entityId];
      const current = after.characters[entityId];
      if (previous && current && previous.sanity !== current.sanity) {
        push({ id: `${entityId}:sanity`, actorId: entityId, name, kind: 'sanity_changed', from: previous.sanity, to: current.sanity });
      }
      for (const taskId of delta.tasksAchieved ?? []) {
        const goal = previous?.tasks[taskId]?.goal ?? current?.tasks[taskId]?.goal;
        if (!goal || current?.tasks[taskId]?.status !== 'achieved') continue;
        push({ id: `${entityId}:task:${taskId}`, actorId: entityId, name, kind: 'task_achieved', taskId, goal });
      }
      for (const change of delta.personalityChanges ?? []) {
        const stored = changes(after, entityId).find((entry) => entry.id === change.id);
        const text = (change.text && change.text.trim())
          || (changes(before ?? after, entityId).find((entry) => entry.id === change.id)?.text ?? '');
        if (!text.trim() || !stored) continue;
        push({ id: `${entityId}:change:${change.id}`, actorId: entityId, name, kind: 'personality_changed', changeId: change.id, text });
      }
    }
  }

  // Backdrop for the scene the reader actually sees: the viewpoint and the
  // people/items in its room. These are `at` facts (optional), so they license
  // the room name without requiring a roll-call in the prose.
  const viewRoom = roomAfter(view);
  if (viewRoom) {
    const viewName = after.initial.characters[view]?.name ?? view;
    push({ id: `${view}:position`, actorId: view, name: viewName, kind: 'at', locationId: viewRoom, location: nameOf(after, viewRoom) });
    push({ id: `${view}:sanity`, actorId: view, name: viewName, kind: 'sanity', value: after.characters[view]?.sanity ?? 0 });
    for (const id of Object.keys(after.characters)) {
      if (roomAfter(id) !== viewRoom) continue;
      const name = after.initial.characters[id].name;
      push({ id: `${id}:position`, actorId: id, name, kind: 'at', locationId: viewRoom, location: nameOf(after, viewRoom) });
    }
    for (const id of Object.keys(after.items)) {
      if (roomAfter(id) !== viewRoom) continue;
      push({ id: `${id}:position`, actorId: id, name: after.initial.items[id].name, kind: 'at', locationId: viewRoom, location: nameOf(after, viewRoom) });
    }
  }

  return {
    anchor: { worldId: after.worldId, pointId: point.pointId, version: 0, stateDigest: '', previousPointId: null },
    facts,
  };
}

export function narrationScene(point: NarrationPoint): BeatSceneContext {
  const { after } = point;
  const view = after.protagonistId;
  const room = visibleRoomOf(after, view);
  if (!room) return { previousAction: point.playerInput ?? undefined };
  const name = nameOf(after, room);
  const presentIds = new Set<Id>([
    view,
    ...Object.keys(after.characters).filter((id) => visibleRoomOf(after, id) === room),
  ]);
  const inRoomCharacters = Object.keys(after.characters)
    .filter((id) => id !== view && visibleRoomOf(after, id) === room)
    .map((id) => ({
      name: after.initial.characters[id].name,
      note: activeNotes(after, id, after.initial.characters[id].initialAppearance)[0],
    }));
  // Carried items are visible only when their carrier is in this room; a
  // character two rooms away must not license their inventory here.
  const carried = Object.keys(after.items).filter((id) => presentIds.has(after.items[id].position.containerId));
  const objects = Object.keys(after.items)
    .filter((id) => visibleRoomOf(after, id) === room || carried.includes(id))
    .slice(0, 8)
    .map((id) => ({
      name: after.initial.items[id].name,
      note: activeNotes(after, id, after.initial.items[id].initialAppearance)[0],
    }));
  return {
    location: name,
    placeNotes: activeNotes(after, room, after.initial.locations[room]?.initialAppearance ?? '').slice(0, 3),
    present: inRoomCharacters,
    objects,
    previousAction: point.playerInput ?? undefined,
  };
}

export function narrationPolicy(point: NarrationPoint, limits: {
  temperature?: number; retryTemperature?: number; maxTokens?: number; maxTokensCeiling?: number;
  timeoutMs?: number; deadlineMs?: number; minChars?: number; targetChars?: number;
} = {}): NarrationPolicy {
  const { after } = point;
  const view = after.protagonistId;
  const room = visibleRoomOf(after, view);
  const viewName = after.initial.characters[view]?.name ?? view;
  const inRoom = Object.keys(after.characters).filter((id) => id !== view && visibleRoomOf(after, id) === room);
  const presentIds = new Set<Id>([view, ...inRoom]);
  const carried = Object.keys(after.items).filter((id) => presentIds.has(after.items[id].position.containerId));
  const time = point.delta.timeAdvance ?? null;
  const playerInput = point.playerInput ?? '';
  return {
    viewpoint: { id: view, name: viewName },
    roster: Object.values(after.initial.characters).map((entity) => entity.name),
    locations: Object.values(after.initial.locations).map((entity) => entity.name),
    knownPositions: inRoom.map((id) => ({ name: after.initial.characters[id].name, location: room ? nameOf(after, room) : '' })),
    knownEntities: [
      ...Object.values(after.initial.characters).map((entity) => entity.name),
      ...Object.values(after.initial.locations).map((entity) => entity.name),
      ...Object.values(after.initial.items).map((entity) => entity.name),
    ],
    visibleEntities: Object.keys(after.items)
      .filter((id) => visibleRoomOf(after, id) === room || carried.includes(id))
      .map((id) => after.initial.items[id].name),
    licensedEvents: EVENT_VERBS.filter((verb) => playerInput.includes(verb)),
    time,
    requireTime: Boolean(time && time.boundary === 'elapsed' && time.duration.amount > 0),
    minChars: limits.minChars ?? 120,
    targetChars: limits.targetChars ?? 240,
    maxTokens: limits.maxTokens ?? 200,
    maxTokensCeiling: limits.maxTokensCeiling ?? 500,
    temperature: limits.temperature ?? 0.7,
    retryTemperature: limits.retryTemperature ?? 0.5,
    timeoutMs: limits.timeoutMs ?? 150_000,
    deadlineMs: limits.deadlineMs ?? 300_000,
  };
}

/** Serialize the point with lane 01's result renderer. A refusal is reported,
 * never repaired locally: a broken projection must not become a made-up input. */
export function serializeNarrationInput(point: NarrationPoint): { text: string | null; error: string | null } {
  if (!point.before) return { text: null, error: 'no_before_state' };
  try {
    const projected = projectNarrationInput({
      before: point.before,
      after: point.after,
      delta: point.delta.entityDeltas ?? {},
      timeAdvance: point.delta.timeAdvance ?? INSTANT,
      viewpointId: point.after.protagonistId,
    });
    const rendered = renderResultInput(projected.projection);
    return { text: rendered.text, error: null };
  } catch (error) {
    const code = error instanceof Error ? `${error.name}:${error.message}` : String(error);
    return { text: null, error: code };
  }
}

export function prepareNarration(point: NarrationPoint, limits: Parameters<typeof narrationPolicy>[1] = {}): PreparedNarration {
  const facts = projectNarrationFacts(point);
  const input = serializeNarrationInput(point);
  const view = point.after.protagonistId;
  return {
    facts,
    inputText: input.text,
    inputError: input.error,
    policy: narrationPolicy(point, limits),
    scene: narrationScene(point),
    viewpointId: view,
    viewpointName: point.after.initial.characters[view]?.name ?? view,
    mandatoryFactIds: facts.facts.filter((fact) => MANDATORY.has(fact.kind)).map((fact) => fact.id),
  };
}
