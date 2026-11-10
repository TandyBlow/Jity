/** Committed point -> read-only scene skeleton.
 *
 * The only inputs are the saved `get_state` records of this point and its
 * predecessor. Nothing is invented: names, descriptions and facts come from
 * the settled state and that point's Δ. Out-of-scene changes are kept as
 * `hidden` facts so the omission is visible in evidence, not silent.
 */
import type {
  Change, EntityDelta, Id, Position, StoredChange, Task, TimeAdvance, WorldState,
} from '../../../types';
import type { CommittedRead, CommittedNarration, NarrationFact } from '../../../runtime/committed-narration';
import { activeText, locationName, roomOf } from '../../prompt';
import type {
  FactVisibility, SceneFact, SceneKnowledge, SceneObject, ScenePerson, SceneSkeleton,
} from './types';

export class SceneProjectionError extends Error {
  readonly name = 'SceneProjectionError';
  constructor(readonly code: string, detail: string) {
    super(`${code}: ${detail}`);
  }
}

const same = (a: unknown, b: unknown): boolean => JSON.stringify(a) === JSON.stringify(b);

export interface ProjectSceneOptions {
  viewpointId?: Id;
  /** Already-settled description overrides; never a new fact. */
  scene?: import('./types').SceneHints;
  knowledge?: Partial<SceneKnowledge>;
  resultsText?: string | null;
  priorText?: string | null;
  inputText?: string | null;
  /** Prefix for fact ids; keeps two projections of the same point distinct. */
  idPrefix?: string;
}

const emptyKnowledge = (): SceneKnowledge => ({ discoveredItemIds: [], visitedLocationIds: [], metCharacterIds: [] });

/** Character/item/location display name from the immutable initial table. */
export function entityName(state: WorldState, id: Id): string {
  return state.initial.characters[id]?.name
    ?? state.initial.items[id]?.name
    ?? state.initial.locations[id]?.name
    ?? id;
}

export function entityKindOf(state: WorldState, id: Id): 'character' | 'item' | 'location' | 'unknown' {
  if (state.characters[id] || state.initial.characters[id]) return 'character';
  if (state.items[id] || state.initial.items[id]) return 'item';
  if (state.locations[id] || state.initial.locations[id]) return 'location';
  return 'unknown';
}

/** First readable clause of a settled description: keeps the concrete detail
 * without dragging the whole paragraph into a beat. */
export function firstClause(text: string, max = 32): string {
  const clean = text.replace(/\s+/gu, ' ').trim();
  if (!clean) return '';
  const parts = clean.split(/[。；;!?！？]/u).map((part) => part.trim()).filter(Boolean);
  let picked = parts[0] ?? clean;
  const commaParts = picked.split(/[，,]/u);
  if (picked.length > max && commaParts.length > 1) {
    picked = commaParts[0];
    for (let index = 1; index < commaParts.length; index += 1) {
      const next = `${picked}，${commaParts[index]}`;
      if (next.length > max) break;
      picked = next;
    }
  }
  return picked.replace(/[，,、]+$/u, '');
}

/** A settled description kept as a complete sentence. Cutting a rule list at
 * a semicolon would read as if the rest of the rule did not exist, so a too
 * long sentence is shortened at a comma and marked with an ellipsis. */
export function noteClause(text: string, max = 48): string {
  const clean = text.replace(/\s+/gu, ' ').trim();
  if (!clean) return '';
  const end = clean.search(/[。！？!?]/u);
  const sentence = end >= 0 ? clean.slice(0, end) : clean;
  if ([...sentence].length <= max) return sentence.replace(/[，,、；;\s]+$/u, '');
  const cut = [...sentence].slice(0, max).join('');
  const comma = Math.max(cut.lastIndexOf('，'), cut.lastIndexOf('、'), cut.lastIndexOf('；'));
  const kept = (comma > max * 0.4 ? cut.slice(0, comma) : cut).replace(/[，、；]+$/u, '');
  return `${kept}……`;
}

function joinNote(initial: string, changes: StoredChange[], max = 48): string {
  const parts = [initial, ...activeText(changes)].filter((text) => text && text.trim());
  const joined = parts.join('；');
  return joined.length > max ? noteClause(joined, max) : joined;
}

function characterNote(state: WorldState, id: Id): string {
  const initial = state.initial.characters[id];
  if (!initial) return '';
  return joinNote(initial.initialAppearance, state.characters[id]?.appearanceChanges ?? []);
}

function itemNote(state: WorldState, id: Id): string {
  const initial = state.initial.items[id];
  if (!initial) return '';
  return joinNote(initial.initialAppearance, state.items[id]?.appearanceChanges ?? []);
}

function placeNameOf(state: WorldState, id: Id): string {
  return locationName(state, id);
}

function locationNote(state: WorldState, id: Id): string {
  const initial = state.initial.locations[id];
  if (!initial) return '';
  return joinNote(initial.initialAppearance, state.locations[id]?.appearanceChanges ?? [], 160);
}

function positionOf(state: WorldState, id: Id): Position | null {
  return state.characters[id]?.position ?? state.items[id]?.position ?? null;
}

function inView(state: WorldState, id: Id, roomId: Id): boolean {
  return roomOf(state, id) === roomId;
}

function sortedIds(state: WorldState, ids: Iterable<Id>): Id[] {
  return [...new Set(ids)].sort((left, right) => entityName(state, left).localeCompare(entityName(state, right), 'zh'));
}

/** Validate that `after` is a genuine next point of `before` and that every Δ
 * agrees with the saved states. Throws instead of guessing. */
export function validateCommittedRead(after: CommittedRead, before: CommittedRead | null): void {
  if (!after.stateDigest || !after.pointId || !Number.isSafeInteger(after.version) || after.version < 0) {
    throw new SceneProjectionError('anchor_missing', 'pointId/stateDigest/version');
  }
  if (!after.state?.initial || !after.state?.characters || !after.state?.items || !after.state?.locations) {
    throw new SceneProjectionError('state_missing', 'after.state tables');
  }
  if (after.previousPointId === null) {
    if (before !== null || after.version !== 0 || Object.keys(after.entityDeltas ?? {}).length || after.timeAdvance != null) {
      throw new SceneProjectionError('root_record_invalid', 'root point must have no before/delta/time');
    }
    return;
  }
  if (!before) throw new SceneProjectionError('before_missing', `point ${after.pointId} needs its predecessor`);
  if (before.pointId !== after.previousPointId) {
    throw new SceneProjectionError('lineage_mismatch', `${before.pointId} != ${after.previousPointId}`);
  }
  if (before.version + 1 !== after.version) {
    throw new SceneProjectionError('version_mismatch', `${before.version} -> ${after.version}`);
  }
  if (before.state.worldId !== after.state.worldId) throw new SceneProjectionError('world_mismatch', 'worldId');
  if (!same(before.state.initial, after.state.initial)) {
    throw new SceneProjectionError('initial_rewritten', 'initial state changed between points');
  }
  if (after.timeAdvance == null) throw new SceneProjectionError('time_missing', 'non-root point without timeAdvance');
}

function validateDelta(after: CommittedRead, before: CommittedRead | null): void {
  const state = after.state;
  const previous = before?.state ?? null;
  for (const [id, delta] of Object.entries(after.entityDeltas ?? {})) {
    if (delta.entityId !== id) throw new SceneProjectionError('delta_entity_mismatch', id);
    const kind = entityKindOf(state, id);
    if (kind === 'unknown') throw new SceneProjectionError('delta_unknown_entity', id);
    if (kind === 'location') {
      if (delta.positionSet != null || delta.sanitySet != null || (delta.tasksAchieved?.length ?? 0)
        || (delta.subtasksAdded?.length ?? 0) || (delta.personalityChanges?.length ?? 0)) {
        throw new SceneProjectionError('delta_location_field', id);
      }
    }
    if (kind === 'item') {
      if (delta.sanitySet != null || (delta.tasksAchieved?.length ?? 0) || (delta.subtasksAdded?.length ?? 0)
        || (delta.personalityChanges?.length ?? 0)) {
        throw new SceneProjectionError('delta_item_field', id);
      }
    }
    if (delta.positionSet != null) {
      const current = positionOf(state, id);
      if (!current || !same(current, delta.positionSet)) {
        throw new SceneProjectionError('delta_position_disagrees', id);
      }
    }
    if (kind === 'character' && delta.sanitySet != null && state.characters[id].sanity !== delta.sanitySet) {
      throw new SceneProjectionError('delta_sanity_disagrees', id);
    }
    for (const taskId of delta.tasksAchieved ?? []) {
      const task = state.characters[id]?.tasks[taskId];
      if (!task || task.status !== 'achieved' || task.ownerId !== id) {
        throw new SceneProjectionError('delta_task_disagrees', `${id}/${taskId}`);
      }
    }
    for (const task of delta.subtasksAdded ?? []) {
      const stored = state.characters[id]?.tasks[task.id];
      if (!stored || stored.ownerId !== id || stored.goal !== task.goal) {
        throw new SceneProjectionError('delta_subtask_disagrees', `${id}/${task.id}`);
      }
    }
    for (const change of delta.appearanceChanges ?? []) {
      const records = kind === 'character' ? state.characters[id].appearanceChanges
        : kind === 'item' ? state.items[id].appearanceChanges : state.locations[id].appearanceChanges;
      const stored = records.find((record) => record.id === change.id);
      if (!stored || stored.text !== (change.text ?? null)) {
        throw new SceneProjectionError('delta_appearance_disagrees', `${id}/${change.id}`);
      }
    }
    for (const change of delta.personalityChanges ?? []) {
      const stored = state.characters[id]?.personalityChanges.find((record) => record.id === change.id);
      if (!stored || stored.text !== (change.text ?? null)) {
        throw new SceneProjectionError('delta_personality_disagrees', `${id}/${change.id}`);
      }
    }
    if (previous) {
      const beforeEntity = previous.characters[id] ?? previous.items[id] ?? previous.locations[id];
      const afterEntity = state.characters[id] ?? state.items[id] ?? state.locations[id];
      if (!beforeEntity || !afterEntity) throw new SceneProjectionError('entity_roster_changed', id);
    }
  }
}

function moveFact(
  after: CommittedRead,
  before: CommittedRead,
  id: Id,
  delta: EntityDelta,
  roomBefore: Id,
  roomAfter: Id,
  prefix: string,
  viewpointId: Id,
): SceneFact | null {
  if (delta.positionSet == null) return null;
  const previousPosition = positionOf(before.state, id);
  if (!previousPosition) return null;
  // A slot-only change (same container) is not a move: nothing changed place.
  if (previousPosition.containerId === delta.positionSet.containerId) return null;
  const kind = entityKindOf(after.state, id);
  if (kind === 'location' || kind === 'unknown') return null;
  const name = entityName(after.state, id);
  const fromVisibility = inView(before.state, id, roomBefore) ? 'in_view' : 'out_of_view';
  const toVisibility = inView(after.state, id, roomAfter) ? 'in_view' : 'out_of_view';
  return {
    id: `${prefix}:move:${id}`,
    kind: 'move',
    mandatory: true,
    // A move is narrated only when the viewpoint can see either endpoint.
    visibility: fromVisibility === 'in_view' || toVisibility === 'in_view' ? 'scene' : 'hidden',
    entityId: id,
    name,
    entityKind: kind,
    fromId: previousPosition.containerId,
    from: locationName(after.state, previousPosition.containerId),
    toId: delta.positionSet.containerId,
    to: locationName(after.state, delta.positionSet.containerId),
    fromVisibility,
    toVisibility,
    viewpoint: id === viewpointId,
  };
}

function changeFactBase(id: Id, prefix: string): string {
  return `${prefix}:change:${id}`;
}

export interface ProjectedScene {
  scene: SceneSkeleton;
  base: CommittedNarration;
}

export function projectConstrainedScene(
  after: CommittedRead,
  before: CommittedRead | null,
  options: ProjectSceneOptions = {},
): ProjectedScene {
  validateCommittedRead(after, before);
  validateDelta(after, before);
  const state = after.state;
  const viewpointId = options.viewpointId ?? state.protagonistId;
  if (!state.characters[viewpointId]) throw new SceneProjectionError('viewpoint_unknown', viewpointId);
  const prefix = options.idPrefix ?? after.pointId;
  const roomAfter = roomOf(state, viewpointId);
  const roomBefore = before ? roomOf(before.state, viewpointId) : roomAfter;
  const knowledge: SceneKnowledge = { ...emptyKnowledge(), ...(options.knowledge ?? {}) };
  const facts: SceneFact[] = [];
  const deltas = after.entityDeltas ?? {};

  // ---- time ----------------------------------------------------------------
  const advance = after.timeAdvance ?? null;
  const hasElapsed = advance != null && advance.duration.amount > 0;
  if (hasElapsed) {
    facts.push({ id: `${prefix}:time`, kind: 'time', mandatory: true, visibility: 'scene', advance });
  }

  // ---- moves ---------------------------------------------------------------
  const moveIds: Id[] = [];
  for (const id of Object.keys(deltas)) {
    if (!before) break;
    const fact = moveFact(after, before, id, deltas[id], roomBefore, roomAfter, prefix, viewpointId);
    if (fact) {
      facts.push(fact);
      moveIds.push(id);
    }
  }

  // ---- per-entity changes --------------------------------------------------
  for (const [id, delta] of Object.entries(deltas)) {
    const kind = entityKindOf(state, id);
    if (kind === 'unknown') continue;
    const name = entityName(state, id);
    const visibleAfter = kind === 'location' ? id === roomAfter : inView(state, id, roomAfter);
    const visibility: FactVisibility = visibleAfter ? 'scene' : 'hidden';
    if (kind !== 'character' && (delta.tasksAchieved?.length || delta.subtasksAdded?.length
      || delta.personalityChanges?.length || delta.sanitySet != null)) {
      continue;
    }

    for (const change of delta.appearanceChanges ?? []) {
      const records = kind === 'character' ? state.characters[id].appearanceChanges
        : kind === 'item' ? state.items[id].appearanceChanges : state.locations[id].appearanceChanges;
      const stored = records.find((record) => record.id === change.id);
      const supersededTexts = change.supersedes
        .map((oldId) => records.find((record) => record.id === oldId)?.text ?? (before
          ? (kind === 'character' ? before.state.characters[id]?.appearanceChanges
            : kind === 'item' ? before.state.items[id]?.appearanceChanges
              : before.state.locations[id]?.appearanceChanges)?.find((record) => record.id === oldId)?.text ?? null
          : null))
        .filter((text): text is string => Boolean(text));
      facts.push({
        id: changeFactBase(change.id, prefix),
        kind: 'appearance_changed',
        mandatory: true,
        visibility,
        entityId: id,
        name,
        entityKind: kind,
        changeId: change.id,
        text: change.text ?? null,
        removed: change.text == null,
        supersededTexts,
      });
      void stored;
    }

    if (kind !== 'character') continue;
    const character = state.characters[id];

    for (const taskId of delta.tasksAchieved ?? []) {
      const task = character.tasks[taskId];
      if (!task) continue;
      facts.push({
        id: `${prefix}:task:${id}:${taskId}`, kind: 'task_achieved', mandatory: true, visibility,
        ownerId: id, name, taskId, goal: task.goal,
      });
    }
    for (const task of delta.subtasksAdded ?? []) {
      const parent = task.parentTaskId ? character.tasks[task.parentTaskId] : null;
      facts.push({
        id: `${prefix}:subtask:${id}:${task.id}`, kind: 'subtask_added', mandatory: true, visibility,
        ownerId: id, name, taskId: task.id, parentTaskId: task.parentTaskId,
        parentGoal: parent?.goal ?? null, goal: task.goal,
      });
    }
    for (const change of delta.personalityChanges ?? []) {
      const records = character.personalityChanges;
      const supersededTexts = change.supersedes
        .map((oldId) => records.find((record) => record.id === oldId)?.text
          ?? before?.state.characters[id]?.personalityChanges.find((record) => record.id === oldId)?.text ?? null)
        .filter((text): text is string => Boolean(text));
      facts.push({
        id: changeFactBase(change.id, prefix), kind: 'personality_changed', mandatory: true, visibility,
        ownerId: id, name, changeId: change.id, text: change.text ?? '', removed: change.text == null,
        supersededTexts,
      });
    }
    if (delta.sanitySet != null && before) {
      const previous = before.state.characters[id];
      if (previous && previous.sanity !== delta.sanitySet) {
        facts.push({
          id: `${prefix}:sanity:${id}`, kind: 'sanity_changed', mandatory: true, visibility,
          ownerId: id, name, from: previous.sanity, to: delta.sanitySet,
        });
      }
    }
  }

  // ---- scene material ------------------------------------------------------
  const present: ScenePerson[] = sortedIds(state, Object.keys(state.characters)).filter((id) => id !== viewpointId && inView(state, id, roomAfter))
    .map((id) => ({ id, name: entityName(state, id), note: characterNote(state, id), viewpoint: false }));
  // Room objects only: items inside a character or a container are licensed
  // through that entity's note, not as furniture of the room.
  const objectIds = sortedIds(state, Object.keys(state.items)).filter((id) => positionOf(state, id)?.containerId === roomAfter);
  const objects: SceneObject[] = objectIds.map((id) => ({ id, name: entityName(state, id), note: itemNote(state, id) }));
  const objectById = new Map(objects.map((object) => [object.id, object]));
  const movedSet = new Set(moveIds);

  // Objects whose visibility changed because a container moved are derived
  // from the saved positions of the two points; they are optional texture.
  const known = new Set(knowledge.discoveredItemIds);
  const root = before === null;
  for (const id of objectIds) {
    if (movedSet.has(id)) continue;
    const visibleBefore = before ? before.state.items[id]?.position.containerId === roomBefore : false;
    if (visibleBefore) continue;
    const object = objectById.get(id)!;
    const containerId = positionOf(state, id)?.containerId ?? roomAfter;
    facts.push({
      id: `${prefix}:present:${id}`, kind: root || known.has(id) ? 'item_present' : 'item_discovered',
      mandatory: false, visibility: 'scene', itemId: id, name: object.name,
      containerId, container: locationName(state, containerId), note: object.note,
    });
  }
  // Present characters are licensed positions (not changes): the prose may say
  // they are here without claiming they moved.
  for (const person of present) {
    // A character who moved this point is licensed by the move fact itself; an
    // extra at-fact would make the move sentence look like an invented arrival
    // (the base grader treats at + movement verb as a fabricated move).
    if (movedSet.has(person.id)) continue;
    facts.push({
      id: `${prefix}:at:${person.id}`, kind: 'at', mandatory: false, visibility: 'scene',
      entityId: person.id, name: person.name, locationId: roomAfter, location: placeNameOf(state, roomAfter),
    });
  }
  if (!movedSet.has(viewpointId)) {
    facts.push({
      id: `${prefix}:at:${viewpointId}`, kind: 'at', mandatory: false, visibility: 'scene',
      entityId: viewpointId, name: entityName(state, viewpointId), locationId: roomAfter, location: locationName(state, roomAfter),
    });
  }

  // ---- settled result wording ---------------------------------------------
  // The settlement's own result line is a fact-bearing description, not a
  // model free-write: it is licensed verbatim so a question/answer or a
  // hand-off does not disappear from the prose.
  if (options.resultsText && options.resultsText.trim()) {
    facts.push({
      id: `${prefix}:result`, kind: 'result', mandatory: true, visibility: 'scene',
      text: clampSentences(options.resultsText, 2, 130),
    });
  }

  // ---- licensing -----------------------------------------------------------
  const names = new Set<string>([entityName(state, viewpointId)]);
  const locations = new Set<string>([locationName(state, roomAfter)]);
  const items = new Set<string>();
  const details = new Set<string>();
  const quotes = new Set<string>();
  for (const person of present) { names.add(person.name); if (person.note) details.add(person.note); }
  for (const object of objects) { items.add(object.name); if (object.note) details.add(object.note); }
  for (const fact of facts) {
    // Hidden changes are evidence only: they may not license a name, quote or
    // detail the viewpoint could not perceive.
    if (fact.visibility !== 'scene') continue;
    switch (fact.kind) {
      case 'move':
        names.add(fact.name);
        locations.add(fact.from);
        locations.add(fact.to);
        if (fact.entityKind === 'item') items.add(fact.name);
        break;
      case 'task_achieved':
        names.add(fact.name);
        quotes.add(fact.goal);
        break;
      case 'subtask_added':
        names.add(fact.name);
        quotes.add(fact.goal);
        if (fact.parentGoal) quotes.add(fact.parentGoal);
        break;
      case 'personality_changed':
        names.add(fact.name);
        if (fact.text) { details.add(fact.text); quotes.add(fact.text); }
        for (const text of fact.supersededTexts) details.add(text);
        break;
      case 'appearance_changed':
        names.add(fact.name);
        if (fact.entityKind === 'item') items.add(fact.name);
        if (fact.entityKind === 'location') locations.add(fact.name);
        if (fact.text) details.add(fact.text);
        for (const text of fact.supersededTexts) details.add(text);
        break;
      case 'sanity_changed':
        names.add(fact.name);
        break;
      case 'item_present':
      case 'item_discovered':
        items.add(fact.name);
        if (fact.note) details.add(fact.note);
        break;
      case 'at':
        names.add(fact.name);
        locations.add(fact.location);
        break;
      case 'result':
        details.add(fact.text);
        quotes.add(fact.text);
        break;
      case 'time':
        break;
    }
  }
  if (options.resultsText) {
    for (const word of options.resultsText.split(/[\s，。；：！？、]+/u)) {
      if (names.has(word) || locations.has(word) || items.has(word)) details.add(word);
    }
  }

  const placeName = locationName(state, roomAfter);
  const placeNote = options.scene?.placeNote ?? locationNote(state, roomAfter);
  const presentWithHints: ScenePerson[] = present.map((person) => ({
    ...person,
    note: options.scene?.presentNotes?.[person.id] ?? person.note,
  }));
  const objectsWithHints: SceneObject[] = objects.map((object) => ({
    ...object,
    note: options.scene?.objectNotes?.[object.id] ?? object.note,
  }));
  const parentId = state.initial.locations[roomAfter]?.parentLocationId ?? null;

  const scene: SceneSkeleton = {
    anchor: {
      worldId: state.worldId, pointId: after.pointId, version: after.version,
      stateDigest: after.stateDigest, previousPointId: after.previousPointId,
    },
    viewpoint: {
      id: viewpointId, name: entityName(state, viewpointId), locationId: roomAfter, location: placeName,
      note: characterNote(state, viewpointId),
      personality: joinNote(state.initial.characters[viewpointId]?.initialPersonality ?? '',
        state.characters[viewpointId]?.personalityChanges ?? [], 80),
      sanity: state.characters[viewpointId].sanity,
    },
    time: advance,
    place: { id: roomAfter, name: placeName, note: placeNote, parentName: parentId ? locationName(state, parentId) : null },
    present: presentWithHints,
    objects: objectsWithHints,
    facts,
    worldNames: {
      characters: Object.values(state.initial.characters).map((entity) => entity.name),
      locations: Object.values(state.initial.locations).map((entity) => entity.name),
      items: Object.values(state.initial.items).map((entity) => entity.name),
    },
    licensed: {
      names: [...names].sort((a, b) => a.localeCompare(b, 'zh')),
      locations: [...locations].sort((a, b) => a.localeCompare(b, 'zh')),
      items: [...items].sort((a, b) => a.localeCompare(b, 'zh')),
      details: [...details],
      quotes: [...quotes],
    },
    knowledge,
    priorText: options.priorText ?? null,
    inputText: options.inputText ?? null,
    resultsText: options.resultsText ?? null,
    hasSceneMaterial: true,
    timeOnly: !Object.keys(deltas).length,
  };

  return { scene, base: buildBasePacket(scene) };
}

function clampSentences(text: string, maxSentences: number, maxChars: number): string {
  const clean = text.replace(/\s+/gu, ' ').trim();
  const parts = clean.split(/(?<=[。！？])/u).map((part) => part.trim()).filter(Boolean);
  let out = (parts.length ? parts : [clean]).slice(0, maxSentences).join('');
  if ([...out].length > maxChars) {
    const cut = [...out].slice(0, maxChars).join('');
    out = `${cut.replace(/[，、；：]$/u, '')}。`;
  }
  return out;
}

/** Facts the legacy alignment gate can grade without new vocabulary. Sanity is
 * deliberately absent: this route expresses the committed DIRECTION, not the
 * raw number (`policy.sanityStyle: 'number'` restores the numeric statement). */
function buildBasePacket(scene: SceneSkeleton): CommittedNarration {
  const facts: NarrationFact[] = [];
  // The legacy grader splits sentences on terminal punctuation, so frozen text
  // ending with 。 would never bind. Normalise the packet copy only.
  const frozen = (text: string): string => text.replace(/[。！？\s]+$/u, '');
  for (const fact of scene.facts) {
    if (fact.visibility !== 'scene') continue;
    if (fact.kind === 'move') {
      facts.push({
        id: fact.id, actorId: fact.entityId, name: fact.name, kind: 'moved',
        fromId: fact.fromId, from: fact.from, toId: fact.toId, to: fact.to,
      });
    } else if (fact.kind === 'task_achieved') {
      facts.push({ id: fact.id, actorId: fact.ownerId, name: fact.name, kind: 'task_achieved', taskId: fact.taskId, goal: frozen(fact.goal) });
    } else if (fact.kind === 'personality_changed') {
      facts.push({ id: fact.id, actorId: fact.ownerId, name: fact.name, kind: 'personality_changed', changeId: fact.changeId, text: frozen(fact.text) });
    } else if (fact.kind === 'at') {
      // Only the viewpoint's own position fact goes into the legacy packet.
      // Present bystanders are licensed through knownPositions instead; an
      // at-fact per bystander would make every presence sentence look like it
      // re-attributed somebody else's position (actor_swap).
      if (fact.entityId !== scene.viewpoint.id) continue;
      facts.push({ id: fact.id, actorId: fact.entityId, name: fact.name, kind: 'at', locationId: fact.locationId, location: fact.location });
    }
  }
  return { anchor: scene.anchor, facts };
}

/** Facts-only skeleton: used when the caller only has a `CommittedNarration`
 * packet (no full state). It still plans and writes prose, but has no place
 * notes or object material. */
export function projectFromFactsPacket(
  packet: CommittedNarration,
  options: ProjectSceneOptions = {},
): ProjectedScene {
  // The viewpoint is either standing (at) or arriving (moved) this point; a
  // facts-only packet with a pure move still knows who moved and where to.
  const atFact = packet.facts.find((fact) => fact.kind === 'at');
  const movedFact = packet.facts.find((fact) => fact.kind === 'moved');
  const anchorFact = atFact ?? movedFact;
  const viewpointName = anchorFact?.name ?? '主角';
  const location = atFact?.kind === 'at' ? atFact.location : movedFact?.kind === 'moved' ? movedFact.to : '';
  if (!location) throw new SceneProjectionError('facts_packet_without_scene', 'needs an at-fact or a moved-fact for the viewpoint');
  const facts: SceneFact[] = [];
  for (const fact of packet.facts) {
    if (fact.kind === 'at' && fact.name === viewpointName) continue;
    if (fact.kind === 'at') {
      facts.push({ id: fact.id, kind: 'at', mandatory: false, visibility: 'scene', entityId: fact.actorId, name: fact.name, locationId: fact.locationId, location: fact.location });
    } else if (fact.kind === 'moved') {
      facts.push({
        id: fact.id, kind: 'move', mandatory: true, visibility: 'scene', entityId: fact.actorId, name: fact.name,
        entityKind: 'character', fromId: fact.fromId, from: fact.from, toId: fact.toId, to: fact.to,
        fromVisibility: 'in_view', toVisibility: 'in_view', viewpoint: fact.name === viewpointName,
      });
    } else if (fact.kind === 'task_achieved') {
      facts.push({ id: fact.id, kind: 'task_achieved', mandatory: true, visibility: 'scene', ownerId: fact.actorId, name: fact.name, taskId: fact.taskId, goal: fact.goal });
    } else if (fact.kind === 'personality_changed') {
      facts.push({ id: fact.id, kind: 'personality_changed', mandatory: true, visibility: 'scene', ownerId: fact.actorId, name: fact.name, changeId: fact.changeId, text: fact.text, removed: false, supersededTexts: [] });
    } else if (fact.kind === 'sanity_changed') {
      facts.push({ id: fact.id, kind: 'sanity_changed', mandatory: true, visibility: 'scene', ownerId: fact.actorId, name: fact.name, from: fact.from, to: fact.to });
    } else if (fact.kind === 'sanity') {
      // unchanged value: not a fact to narrate
    }
  }
  // Present characters come from the packet's own at-facts (the shared driver
  // emits one per character in the room). They are licensed presence, not a
  // change.
  const present: ScenePerson[] = [];
  for (const fact of packet.facts) {
    if (fact.kind !== 'at' || fact.name === viewpointName) continue;
    if (present.some((person) => person.id === fact.actorId)) continue;
    present.push({ id: fact.actorId, name: fact.name, note: '', viewpoint: false });
  }
  const scene: SceneSkeleton = {
    anchor: packet.anchor,
    viewpoint: {
      id: anchorFact?.kind === 'at' ? anchorFact.actorId : 'viewpoint',
      name: viewpointName, locationId: anchorFact?.kind === 'at' ? anchorFact.locationId : '', location,
      note: '', personality: '', sanity: 0,
    },
    time: options.priorText != null ? null : null,
    place: { id: '', name: location, note: '', parentName: null },
    present,
    objects: [],
    facts,
    licensed: {
      names: [...new Set(packet.facts.map((fact) => fact.name))],
      locations: [...new Set(packet.facts.flatMap((fact) => fact.kind === 'moved' ? [fact.from, fact.to] : fact.kind === 'at' ? [fact.location] : []))],
      items: [], details: [], quotes: [...new Set(packet.facts.flatMap((fact) => fact.kind === 'task_achieved' ? [fact.goal] : []))],
    },
    knowledge: { ...emptyKnowledge(), ...(options.knowledge ?? {}) },
    priorText: options.priorText ?? null,
    inputText: options.inputText ?? null,
    resultsText: options.resultsText ?? null,
    worldNames: { characters: [], locations: [], items: [] },
    hasSceneMaterial: present.length > 0,
    timeOnly: !facts.some((fact) => fact.kind !== 'time' && fact.kind !== 'at'),
  };
  return { scene, base: packet };
}

export type { Change, Task, TimeAdvance };
