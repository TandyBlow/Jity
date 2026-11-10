/** Compatibility adapter for a committed fact packet plus the read-only state.
 *
 * Facts come from `committed.facts` (the authority). The optional `state` read
 * supplies scene material only: the viewpoint's location, who is present, the
 * settled appearance texts and the items lying in the room. It never derives a
 * fact from the state; if no state is supplied the skeleton stays sparse and
 * the composer reports that honestly.
 *
 * This is also the product entry: the shared browser driver already passes
 * `committed`, `state`, `before`, and the time advance, so a caller does not
 * need lane 04's richer skeleton to get real prose.
 */

import { hash32 } from './support';
import type { ProseActor, ProseBeat, ProseItem, ProseScene } from './types';

export interface CommittedFactLike {
  id: string;
  actorId: string;
  name: string;
  kind: 'at' | 'moved' | 'sanity' | 'sanity_changed' | 'task_achieved' | 'personality_changed' | 'appearance_changed';
  location?: string;
  from?: string;
  to?: string;
  value?: number;
  fromValue?: number;
  toValue?: number;
  goal?: string;
  text?: string;
}

export interface CommittedLike {
  anchor?: { worldId?: string; pointId?: string };
  facts: CommittedFactLike[];
  /** Present on a CommittedScenePacket; used only when `state` is absent. */
  timeAdvance?: { duration: { amount: number; unit: 'second' | 'minute' | 'hour' | 'day' | 'month' | 'year' } } | null;
  /** The shared browser driver attaches the same settled read to the packet. */
  state?: WorldStateLike | null;
  beforeState?: WorldStateLike | null;
  entityDeltas?: Record<string, { positionSet?: unknown; appearanceChanges?: unknown[] }>;
}

export interface ChangeLike {
  id: string;
  text: string | null;
  supersedes?: string[];
  active?: boolean;
}

export interface EntityReadLike {
  id?: string;
  position?: { containerId?: string } | null;
  appearanceChanges?: ChangeLike[];
  personalityChanges?: ChangeLike[];
  sanity?: number;
}

/** The subset of WorldState the adapter reads. Structural on purpose: no
 * cross-lane import, and an unexpected shape simply yields a sparse scene. */
export interface WorldStateLike {
  worldId: string;
  protagonistId: string;
  initial: {
    locations: Record<string, { id: string; name: string; parentLocationId?: string | null; initialAppearance?: string }>;
    characters: Record<string, { id: string; name: string; initialAppearance?: string }>;
    items: Record<string, { id: string; name: string; initialAppearance?: string }>;
  };
  characters: Record<string, EntityReadLike>;
  items: Record<string, EntityReadLike>;
}

export interface CommittedAdapterPolicy {
  viewpoint?: { id?: string; name: string } | null;
  priorText?: string | null;
  seed?: number;
  minChars?: number;
  state?: WorldStateLike | null;
  timeAdvance?: CommittedLike['timeAdvance'];
  delta?: { timeAdvance?: CommittedLike['timeAdvance'] } | null;
  /** The settled read before the point, when the caller has it. Changes the
   * committed packet leaves out (sanity, appearance, personality) are read from
   * this pair instead of being lost. */
  beforeState?: WorldStateLike | null;
  /** Session transcript, when the caller has it. */
  avoidText?: string | null;
}

export interface AdaptedScene {
  scene: ProseScene;
  /** True when no state read was available, so scene material is missing. */
  sparse: boolean;
}

function entityName(state: WorldStateLike, kind: 'locations' | 'characters' | 'items', id: string): string {
  return state.initial[kind][id]?.name ?? id;
}

/** Initial appearance plus the active settled changes. A change is inactive
 * when another change supersedes its id, or when the record says so. */
function appearanceText(changes: ChangeLike[] | undefined, initial: string | undefined): string {
  const list = changes ?? [];
  const superseded = new Set(list.flatMap((change) => change.supersedes ?? []));
  const parts = [initial ?? ''];
  for (const change of list) {
    if (change.active === false) continue;
    if (change.active !== true && superseded.has(change.id)) continue;
    if (change.text && change.text.trim()) parts.push(change.text.trim());
  }
  return parts.filter(Boolean).join('；');
}

function presentCharacters(state: WorldStateLike, locationId: string): string[] {
  return Object.keys(state.characters)
    .filter((id) => state.characters[id]?.position?.containerId === locationId)
    .sort((left, right) => entityName(state, 'characters', left).localeCompare(entityName(state, 'characters', right), 'zh'));
}

function presentItems(state: WorldStateLike, locationId: string): string[] {
  return Object.keys(state.items)
    .filter((id) => state.items[id]?.position?.containerId === locationId)
    .sort((left, right) => entityName(state, 'items', left).localeCompare(entityName(state, 'items', right), 'zh'));
}

function sceneFromState(
  committed: CommittedLike,
  state: WorldStateLike,
  policy: CommittedAdapterPolicy,
): { scene: ProseScene; sparse: boolean } | null {
  const protagonistId = policy.viewpoint?.id ?? state.protagonistId;
  if (!state.initial.characters[protagonistId]) return null;
  const locationId = state.characters[protagonistId]?.position?.containerId;
  const location = locationId ? state.initial.locations[locationId] : undefined;
  if (!locationId || !location) return null;
  const parentName = location.parentLocationId
    ? entityName(state, 'locations', location.parentLocationId)
    : null;
  const cast: ProseActor[] = presentCharacters(state, locationId).map((id) => ({
    id,
    name: entityName(state, 'characters', id),
    gender: 'unknown' as const,
    appearance: [appearanceText(state.characters[id]?.appearanceChanges, state.initial.characters[id]?.initialAppearance)]
      .filter(Boolean),
    isProtagonist: id === protagonistId,
  }));
  const items: ProseItem[] = presentItems(state, locationId).map((id) => ({
    id,
    name: entityName(state, 'items', id),
    details: [appearanceText(state.items[id]?.appearanceChanges, state.initial.items[id]?.initialAppearance)]
      .filter(Boolean),
    positionName: location.name,
  }));
  const scene: ProseScene = {
    worldId: committed.anchor?.worldId ?? state.worldId,
    pointId: committed.anchor?.pointId,
    protagonistId,
    location: {
      id: locationId,
      name: location.name,
      parentName,
      details: [location.initialAppearance ?? ''].filter(Boolean),
    },
    parentLocation: parentName ? { name: parentName, details: [] } : null,
    cast,
    items,
    beats: [],
    priorText: policy.priorText ?? null,
    policy: { minChars: policy.minChars ?? 60, requireTime: true },
    seed: policy.seed,
  };
  return { scene, sparse: false };
}

/** One clause of a settled description, so a scene beat does not paste a whole
 * paragraph of scenery into the prose. */
function clause(text: string | undefined, max = 40): string {
  const clean = (text ?? '').replace(/\s+/gu, ' ').trim();
  if (!clean) return '';
  if ([...clean].length <= max) return clean.replace(/[。；]+$/u, '');
  const parts = clean.split(/[。；;]/u).map((part) => part.trim()).filter(Boolean);
  if (parts[0] && [...parts[0]].length <= max) return parts[0];
  const comma = clean.indexOf('，');
  return (comma >= 8 && comma <= max ? clean.slice(0, comma) : clean.slice(0, max)).replace(/[，、]+$/u, '');
}

function sceneTexture(
  scene: ProseScene,
  changedItems: Set<string> = new Set(),
  mentioned: { ids: Set<string>; names: Set<string> } = { ids: new Set(), names: new Set() },
  arrivedHere = false,
  quietTurn = false,
  avoid = '',
): ProseBeat[] {
  const beats: ProseBeat[] = [];
  const seed = scene.seed ?? 0;
  // Present people go into ONE paragraph. A separate "身边还有X" line per
  // person is exactly the state-list tone: it reads as an inventory rather
  // than as a scene.
  // On a continuation the room was already seen. Re-listing everyone who is
  // standing there is the state-list tone; only a turn that arrives somewhere
  // new earns a look around.
  if (scene.priorText && !arrivedHere) {
    // A turn with nothing but the clock moving may hold one settled object the
    // reader has not seen: a true fact, not a repeat and not filler.
    return itemsTexture(scene, changedItems, quietTurn, avoid);
  }
  const people = scene.cast
    .filter((actor) => actor.id !== scene.protagonistId
      && !mentioned.ids.has(actor.id) && !mentioned.names.has(actor.name)
      && !(avoid && avoid.includes(actor.name)))
    .map((actor) => ({ name: actor.name, detail: clause(actor.appearance?.[0], 28) }))
    .filter((person) => person.detail)
    .slice(0, 3);
  if (people.length === 1) {
    const forms = [
      `身边还有${people[0].name}，${people[0].detail}。`,
      `不远处是${people[0].name}，${people[0].detail}。`,
      `近处还有${people[0].name}，${people[0].detail}。`,
    ];
    beats.push({ kind: 'scene', detail: forms[hash32(`${seed}|${people[0].name}|near`) % forms.length] });
  } else if (people.length > 1) {
    const lead = hash32(`${seed}|people|near`) % 2 === 0
      ? `身边还有${people[0].name}，${people[0].detail}`
      : `不远处是${people[0].name}，${people[0].detail}`;
    const rest = people.slice(1).map((person) => `${person.name}，${person.detail}`).join('；');
    beats.push({ kind: 'scene', detail: `${lead}；${rest}。` });
  }
  return [...beats, ...itemsTexture(scene, changedItems, quietTurn, avoid)];
}

/** Objects: a quiet turn may mention ONE settled object; a continuation only an
 * object this turn actually changed. Two "still there" lines in a row are the
 * inventory tone again. */
function itemsTexture(
  scene: ProseScene,
  changedItems: Set<string>,
  quietTurn = true,
  avoid = '',
): ProseBeat[] {
  const beats: ProseBeat[] = [];
  const changed = (scene.items ?? []).filter((item) => changedItems.has(item.id));
  const unseen = (item: { name: string }) => !avoid || !avoid.includes(item.name);
  const unchanged = (scene.items ?? []).filter((item) => !changedItems.has(item.id) && unseen(item));
  const chosen = changed.length
    ? changed.slice(0, scene.priorText ? 1 : 2)
    : (scene.priorText ? (quietTurn ? unchanged.slice(0, 1) : []) : unchanged.slice(0, 1));
  for (const item of chosen) {
    const detail = clause(item.details?.[0]);
    beats.push({
      kind: 'item', itemId: item.id, container: scene.location.name,
      note: detail || undefined,
    });
  }
  return beats;
}

/** People the rendered fact beats already name. Repeating their appearance in
 * the same turn is what makes prose read like a state dump: "诺诺从…来到…"
 * followed by "身边还有诺诺，…". Returns ids and names, since appearance beats
 * carry a name rather than an id. */
function mentionedByBeats(beats: ProseBeat[], scene: ProseScene): { ids: Set<string>; names: Set<string> } {
  const ids = new Set<string>();
  const names = new Set<string>();
  const addName = (name: string | undefined) => {
    if (!name) return;
    names.add(name);
    const actor = scene.cast.find((entry) => entry.name === name);
    if (actor) ids.add(actor.id);
  };
  for (const beat of beats) {
    switch (beat.kind) {
      case 'move': case 'stay': case 'leave': case 'arrive':
      case 'task': case 'subtask': case 'sanity': case 'personality': case 'action': {
        ids.add(beat.actorId);
        const actor = scene.cast.find((entry) => entry.id === beat.actorId);
        if (actor) names.add(actor.name);
        break;
      }
      case 'line':
        ids.add(beat.speakerId);
        break;
      case 'appearance':
        addName((beat as { subjectName?: string }).subjectName);
        break;
      default:
        break;
    }
  }
  return { ids, names };
}

interface FactLookup {
  itemIds: Set<string>;
  names: Map<string, string>;
}

/** Facts identify entities by id only. Items and people who already left the
 * visible scene are still in the fact list, so their kind and name have to come
 * from the world read, not from the current cast. */
function factLookup(scene: ProseScene, state: WorldStateLike | null): FactLookup {
  const itemIds = new Set((scene.items ?? []).map((item) => item.id));
  const names = new Map<string, string>();
  for (const actor of scene.cast ?? []) names.set(actor.id, actor.name);
  type Entities = Record<string, { id?: string; name?: string } | undefined> | undefined;
  const initial = state?.initial as { characters?: unknown; items?: unknown } | undefined;
  // The live read carries positions; the immutable world table is where the
  // names live. Both are consulted so a departed entity keeps its name.
  for (const table of [initial?.characters, state?.characters] as Entities[]) {
    for (const [id, entity] of Object.entries(table ?? {})) {
      if (!entity) continue;
      if (entity.name) names.set(entity.id ?? id, entity.name);
    }
  }
  for (const table of [initial?.items, state?.items] as Entities[]) {
    for (const [id, entity] of Object.entries(table ?? {})) {
      if (!entity) continue;
      itemIds.add(entity.id ?? id);
      if (entity.name) names.set(entity.id ?? id, entity.name);
    }
  }
  return { itemIds, names };
}

function beatsFromFacts(facts: CommittedFactLike[], protagonistId: string, lookup: FactLookup): ProseBeat[] {
  const beats: ProseBeat[] = [];
  for (const fact of facts) {
    if (fact.actorId === protagonistId && fact.kind === 'at') continue;
    switch (fact.kind) {
      case 'moved': {
        const isItem = lookup.itemIds.has(fact.actorId);
        const name = lookup.names.get(fact.actorId);
        const inCast = lookup.names.has(fact.actorId) && !isItem;
        beats.push({
          kind: 'move', actorId: fact.actorId,
          from: fact.from ?? '原来的位置', to: fact.to ?? '别处',
          ...(isItem ? { entityKind: 'item' as const } : {}),
          ...(name ? { actorName: name } : {}),
          ...(!inCast && !isItem && !name ? {} : {}),
        });
        break;
      }
      case 'task_achieved':
        beats.push({ kind: 'task', actorId: fact.actorId, label: fact.goal ?? '手头的事', scope: 'sub' });
        break;
      case 'personality_changed':
        if (fact.text) beats.push({ kind: 'personality', actorId: fact.actorId, text: fact.text });
        break;
      case 'sanity_changed':
        beats.push({
          kind: 'sanity', actorId: fact.actorId,
          from: fact.fromValue ?? fact.value ?? 0, to: fact.toValue ?? fact.value ?? 0,
        });
        break;
      default:
        break;
    }
  }
  return beats;
}

/** Settled changes the committed packet does not carry as facts.
 *
 * 04's packet carries moves, tasks and personality, but a real point can also
 * settle sanity and appearance. Those two only exist in the before/after state
 * read, so the adapter diffs them. Nothing is invented: a value is narrated
 * only when the two reads disagree and the packet did not already say it.
 */
function changeBeatsFromStateDiff(
  before: WorldStateLike | null,
  after: WorldStateLike,
  facts: CommittedFactLike[],
  scene: ProseScene,
): ProseBeat[] {
  if (!before) return [];
  const beats: ProseBeat[] = [];
  const bare = (text: string | undefined) => (text ?? '').replace(/[。！？…\s]+$/u, '');
  const factText = facts
    .filter((fact) => fact.kind === 'personality_changed' || fact.kind === 'appearance_changed')
    .map((fact) => `${fact.actorId}|${bare(fact.text)}`);
  const characterIds = new Set(scene.cast.map((actor) => actor.id));
  for (const [id, live] of Object.entries(after.characters ?? {})) {
    const previous = before.characters?.[id];
    if (!previous || !characterIds.has(id)) continue;
    const name = after.initial.characters[id]?.name ?? id;
    if (typeof previous.sanity === 'number' && typeof live.sanity === 'number'
      && previous.sanity !== live.sanity
      && !facts.some((fact) => fact.kind === 'sanity_changed' && fact.actorId === id)) {
      beats.push({ kind: 'sanity', actorId: id, from: previous.sanity, to: live.sanity });
    }
    const priorIds = new Set((previous.appearanceChanges ?? []).map((change) => change.id));
    for (const change of live.appearanceChanges ?? []) {
      if (priorIds.has(change.id)) continue;
      const text = change.text?.trim();
      if (!text || factText.some((entry) => entry === `${id}|${bare(text)}`)) continue;
      beats.push({ kind: 'appearance', subjectName: name, text, factText: text });
    }
    const priorPersonality = new Set((previous.personalityChanges ?? []).map((change) => change.id));
    for (const change of live.personalityChanges ?? []) {
      if (priorPersonality.has(change.id)) continue;
      const text = change.text?.trim();
      if (!text || factText.some((entry) => entry === `${id}|${bare(text)}`)) continue;
      beats.push({ kind: 'personality', actorId: id, text });
    }
  }
  return beats;
}

export function sceneFromCommitted(
  committed: CommittedLike,
  policy: CommittedAdapterPolicy = {},
): AdaptedScene {
  const facts = committed.facts ?? [];
  const names = new Map<string, string>();
  for (const fact of facts) names.set(fact.actorId, fact.name);
  if (policy.viewpoint?.id && policy.viewpoint.name) {
    names.set(policy.viewpoint.id, policy.viewpoint.name);
  }
  const protagonistId = policy.viewpoint?.id ?? facts[0]?.actorId ?? '';
  const protagonistName = names.get(protagonistId) ?? policy.viewpoint?.name ?? protagonistId;
  const stateRead = policy.state ?? null;
  const enriched = stateRead ? sceneFromState(committed, stateRead, policy) : null;
  const read = stateRead as WorldStateLike | null;
  if (enriched && read) {
    const advance = policy.timeAdvance ?? policy.delta?.timeAdvance ?? committed.timeAdvance ?? null;
    const beats = beatsFromFacts(facts, enriched.scene.protagonistId, factLookup(enriched.scene, read));
    if (policy.beforeState) beats.push(...changeBeatsFromStateDiff(policy.beforeState, read, facts, enriched.scene));
    if (advance?.duration && advance.duration.amount > 0) {
      beats.unshift({ kind: 'time', amount: advance.duration.amount, unit: advance.duration.unit });
    }
    // A continuation whose point settled nothing (for example the settlement
    // failed and only the previous state is available) has nothing to narrate.
    // Describing the unchanged room here would hide the failed turn behind
    // plausible prose; report an empty scene instead so the caller can show a
    // retry. The opening turn has no prior text and is unaffected.
    const hasSettledBeat = beats.some((beat) => beat.kind !== 'scene');
    if (!hasSettledBeat && policy.priorText && !(advance?.duration && advance.duration.amount > 0)) {
      enriched.scene.beats = [];
      return enriched;
    }
    const placeLine = clause(enriched.scene.location.details?.[0], 44);
    // The place is the anchor: it must stay ahead of the presence texture.
    if (placeLine) beats.unshift({ kind: 'scene', detail: placeLine });
    const changedItems = new Set(Object.entries(committed.entityDeltas ?? {})
      .filter(([, delta]) => Boolean(delta?.positionSet) || Boolean(delta?.appearanceChanges?.length))
      .map(([id]) => id));
    const arrivedHere = beats.some((beat) => beat.kind === 'move'
      && beat.actorId === enriched.scene.protagonistId && beat.to === enriched.scene.location.name);
    const quietTurn = beats.every((beat) => beat.kind === 'time' || beat.kind === 'scene');
    const avoid = [policy.priorText ?? '', policy.avoidText ?? ''].filter(Boolean).join(' ');
    enriched.scene.beats = [
      ...beats,
      ...sceneTexture(
        enriched.scene, changedItems, mentionedByBeats(beats, enriched.scene),
        arrivedHere, quietTurn, avoid,
      ),
    ];
    return enriched;
  }
  let locationName: string | undefined;
  for (const fact of facts) {
    if (fact.kind === 'moved' && fact.to) { locationName = fact.to; break; }
    if (fact.kind === 'at' && fact.location && !locationName) locationName = fact.location;
  }
  const beats: ProseBeat[] = [];
  for (const fact of facts) {
    switch (fact.kind) {
      case 'moved':
        beats.push({ kind: 'move', actorId: fact.actorId, from: fact.from ?? '原来的位置', to: fact.to ?? '别处' });
        break;
      case 'task_achieved':
        beats.push({ kind: 'task', actorId: fact.actorId, label: fact.goal ?? '手头的事', scope: 'sub' });
        break;
      case 'personality_changed':
        beats.push({ kind: 'personality', actorId: fact.actorId, text: fact.text ?? '' });
        break;
      case 'sanity_changed':
        beats.push({
          kind: 'sanity', actorId: fact.actorId,
          from: fact.fromValue ?? fact.value ?? 0, to: fact.toValue ?? fact.value ?? 0,
        });
        break;
      default:
        break;
    }
  }
  const sparseAdvance = policy.timeAdvance ?? policy.delta?.timeAdvance ?? committed.timeAdvance ?? null;
  if (sparseAdvance?.duration && sparseAdvance.duration.amount > 0) {
    beats.unshift({ kind: 'time', amount: sparseAdvance.duration.amount, unit: sparseAdvance.duration.unit });
  }
  const cast: ProseActor[] = [...names.entries()].map(([id, name]) => ({
    id, name, isProtagonist: id === protagonistId,
  }));
  const scene: ProseScene = {
    worldId: committed.anchor?.worldId,
    pointId: committed.anchor?.pointId,
    protagonistId: protagonistId || 'protagonist',
    location: {
      name: locationName ?? '这里',
      details: [],
    },
    cast: cast.length ? cast : [{ id: 'protagonist', name: protagonistName, isProtagonist: true }],
    items: [],
    beats,
    priorText: policy.priorText ?? null,
    policy: { minChars: policy.minChars ?? 60, requireTime: true },
    seed: policy.seed,
  };
  return { scene, sparse: true };
}

/** The shared browser driver's `scene` is a grounding, not a ProseScene:
 * location name, place notes, present people, room objects and inventory. */
export interface SceneGroundingLike {
  location: string;
  placeNotes?: string[];
  present?: { id: string; name: string; note?: string }[];
  objects?: { id: string; name: string; note?: string }[];
  inventory?: { id: string; name: string; note?: string }[];
  exits?: string[];
}

/** Build the composer scene from the driver's grounding. Facts still come
 * from the committed packet; the grounding supplies scene material. */
export function sceneFromGrounding(
  grounding: SceneGroundingLike,
  committed: CommittedLike,
  policy: CommittedAdapterPolicy = {},
): AdaptedScene {
  const stateRead = policy.state ?? null;
  const protagonistId = policy.viewpoint?.id
    ?? stateRead?.protagonistId
    ?? committed.facts?.[0]?.actorId
    ?? 'protagonist';
  const protagonistName = policy.viewpoint?.name
    ?? (stateRead ? entityName(stateRead, 'characters', protagonistId) : committed.facts?.[0]?.name)
    ?? protagonistId;
  const cast: ProseActor[] = (grounding.present ?? []).map((person) => ({
    id: person.id,
    name: person.name,
    appearance: person.note ? [person.note] : [],
    isProtagonist: person.id === protagonistId,
  }));
  if (!cast.some((actor) => actor.id === protagonistId)) {
    const appearance = stateRead
      ? appearanceText(stateRead.characters[protagonistId]?.appearanceChanges,
        stateRead.initial.characters[protagonistId]?.initialAppearance)
      : '';
    cast.unshift({
      id: protagonistId, name: protagonistName,
      appearance: appearance ? [appearance] : [], isProtagonist: true,
    });
  }
  // Someone may have left the room this turn; the fact still names them, so
  // they must stay referable even though the grounding no longer lists them.
  for (const fact of committed.facts ?? []) {
    if (!cast.some((actor) => actor.id === fact.actorId)) {
      cast.push({ id: fact.actorId, name: fact.name, isProtagonist: false });
    }
  }
  const here = grounding.location;
  const items: ProseItem[] = (grounding.objects ?? []).map((item) => ({
    id: item.id, name: item.name,
    details: item.note ? [item.note] : [],
    positionName: here,
  }));
  const scene: ProseScene = {
    worldId: committed.anchor?.worldId ?? stateRead?.worldId,
    pointId: committed.anchor?.pointId,
    protagonistId,
    location: { name: here, details: grounding.placeNotes ?? [] },
    cast,
    items,
    beats: [],
    priorText: policy.priorText ?? null,
    // The floor is a broken-output check, not a length target: a real turn can
    // legitimately carry only a place note and one elapsed beat, and padding it
    // with filler to reach 60 characters is exactly what the product forbids.
    policy: { minChars: policy.minChars ?? 12, requireTime: true },
    seed: policy.seed,
  };
  const beats = beatsFromFacts(committed.facts ?? [], protagonistId, factLookup(scene, null));
  const advance = policy.timeAdvance ?? policy.delta?.timeAdvance ?? committed.timeAdvance ?? null;
  if (advance?.duration && advance.duration.amount > 0) {
    beats.unshift({ kind: 'time', amount: advance.duration.amount, unit: advance.duration.unit });
  }
  const placeLine = clause(scene.location.details?.[0], 44);
  if (placeLine) beats.unshift({ kind: 'scene', detail: placeLine });
  const changedItems = new Set(Object.entries(committed.entityDeltas ?? {})
    .filter(([, delta]) => Boolean(delta?.positionSet) || Boolean(delta?.appearanceChanges?.length))
    .map(([id]) => id));
  const arrivedHere = beats.some((beat) => beat.kind === 'move'
    && beat.actorId === protagonistId && beat.to === scene.location.name);
  const quietTurn = beats.every((beat) => beat.kind === 'time' || beat.kind === 'scene');
  const avoid = [policy.priorText ?? '', policy.avoidText ?? ''].filter(Boolean).join(' ');
  scene.beats = [
    ...beats,
    ...sceneTexture(scene, changedItems, mentionedByBeats(beats, scene), arrivedHere, quietTurn, avoid),
  ];
  return { scene, sparse: false };
}

export type { WorldStateLike as WorldState };
