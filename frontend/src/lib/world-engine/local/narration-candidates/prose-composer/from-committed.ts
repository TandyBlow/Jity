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
  kind: 'at' | 'moved' | 'sanity' | 'sanity_changed' | 'task_achieved' | 'personality_changed';
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

function sceneTexture(scene: ProseScene): ProseBeat[] {
  const beats: ProseBeat[] = [];
  const seed = scene.seed ?? 0;
  for (const actor of scene.cast) {
    if (actor.id === scene.protagonistId) continue;
    const detail = clause(actor.appearance?.[0]);
    if (!detail) continue;
    const forms = [
      `身边还有${actor.name}，${detail}。`,
      `不远处是${actor.name}，${detail}。`,
      `近处还有${actor.name}，${detail}。`,
    ];
    beats.push({ kind: 'scene', detail: forms[hash32(`${seed}|${actor.id}|near`) % forms.length] });
  }
  for (const item of (scene.items ?? []).slice(0, 2)) {
    const detail = clause(item.details?.[0]);
    beats.push({
      kind: 'item', itemId: item.id, container: scene.location.name,
      note: detail || undefined,
    });
  }
  return beats;
}

function beatsFromFacts(facts: CommittedFactLike[], protagonistId: string): ProseBeat[] {
  const beats: ProseBeat[] = [];
  for (const fact of facts) {
    if (fact.actorId === protagonistId && fact.kind === 'at') continue;
    switch (fact.kind) {
      case 'moved':
        beats.push({ kind: 'move', actorId: fact.actorId, from: fact.from ?? '原来的位置', to: fact.to ?? '别处' });
        break;
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
  if (enriched) {
    const advance = policy.timeAdvance ?? policy.delta?.timeAdvance ?? committed.timeAdvance ?? null;
    const beats = beatsFromFacts(facts, enriched.scene.protagonistId);
    if (advance?.duration && advance.duration.amount > 0) {
      beats.unshift({ kind: 'time', amount: advance.duration.amount, unit: advance.duration.unit });
    }
    const placeLine = clause(enriched.scene.location.details?.[0], 44);
    // The place is the anchor: it must stay ahead of the presence texture.
    if (placeLine) beats.unshift({ kind: 'scene', detail: placeLine });
    enriched.scene.beats = [...beats, ...sceneTexture(enriched.scene)];
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

export type { WorldStateLike as WorldState };
