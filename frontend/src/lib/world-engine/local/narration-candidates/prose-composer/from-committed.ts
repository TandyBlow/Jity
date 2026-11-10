/** Compatibility adapter for lane 02's `CommittedNarration` packet.
 *
 * This adapter is a convenience for callers that only have the committed fact
 * list. It cannot invent scene appearance: the resulting skeleton is sparse,
 * which the composer will show honestly in its length and issues. Lane 04's
 * richer skeleton should be preferred.
 */

import type { ProseActor, ProseBeat, ProseScene } from './types';

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
}

export interface CommittedAdapterPolicy {
  viewpoint?: { id?: string; name: string } | null;
  priorText?: string | null;
  seed?: number;
  minChars?: number;
}

export interface AdaptedScene {
  scene: ProseScene;
  /** True when the packet carried no named location for the scene anchor. */
  sparse: boolean;
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
    policy: { minChars: policy.minChars ?? 60 },
    seed: policy.seed,
  };
  return { scene, sparse: true };
}
