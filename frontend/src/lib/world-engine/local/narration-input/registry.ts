/** Entity name -> 地点/人物/物品. The registry is the only place that decides
 * a type; the serializer never guesses from a change field. Ported from
 * `v2_render.entity_registry`. */
import type { ProjectionState, ResultState } from './types';
import { NarrationInputError } from './types';
import { cleanIdentifier } from './text-rules';
import { expectObject } from './normalize';

export type EntityType = '地点' | '人物' | '物品';

export const TYPE_OF_BLOCK: Record<'地点' | '人物' | '物品', EntityType> = {
  地点: '地点',
  人物: '人物',
  物品: '物品',
};

export function entityRegistry(
  before: ProjectionState, result?: ResultState,
): Map<string, EntityType> {
  const registry = new Map<string, EntityType>();
  const add = (name: string, kind: EntityType, path: string): void => {
    const previous = registry.get(name);
    if (previous !== undefined && previous !== kind) {
      throw new NarrationInputError('ambiguous_entity', `entity ${JSON.stringify(name)} is both ${previous} and ${kind} (${path})`, path);
    }
    registry.set(name, kind);
  };
  for (const block of ['地点', '人物', '物品'] as const) {
    const entries = expectObject((before as unknown as Record<string, unknown>)[block] ?? {}, `上回合状态/${block}`);
    for (const name of Object.keys(entries)) {
      add(cleanIdentifier(name, `上回合状态/${block}/键`), TYPE_OF_BLOCK[block], `上回合状态/${block}/${name}`);
    }
  }
  if (result && Object.keys(result).length > 0) {
    // Port of the reference: it reads `result.get(block)`, i.e. it expects a
    // block-shaped result. A flat result has no such keys, so this loop adds
    // nothing in the runtime path. Kept literal so a crafted projection
    // behaves exactly like the Python reference.
    for (const block of ['地点', '人物', '物品'] as const) {
      const entries = (result as unknown as Record<string, unknown>)[block];
      if (entries === undefined || entries === null) continue;
      const object = expectObject(entries, `本回合状态/${block}`);
      for (const name of Object.keys(object)) {
        add(cleanIdentifier(name, `本回合状态/${block}/键`), TYPE_OF_BLOCK[block], `本回合状态/${block}/${name}`);
      }
    }
  }
  return registry;
}

export function resolveType(registry: Map<string, EntityType>, name: string, path: string): EntityType {
  const kind = registry.get(name);
  if (kind === undefined) {
    throw new NarrationInputError('unknown_entity', `entity ${JSON.stringify(name)} is not in the before state`, path);
  }
  return kind;
}
