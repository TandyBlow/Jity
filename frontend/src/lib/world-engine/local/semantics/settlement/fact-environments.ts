/** `环境=entity:state` in settled facts; move/transfer is not env. */
import type { Id, WorldState } from '../../../types';

export interface FactEnvironment {
  entityId: string;
  text: string;
}

export function readEnvironments(texts: string[]): FactEnvironment[] {
  const rows: FactEnvironment[] = [];
  for (const text of texts) {
    for (const match of text.matchAll(/环境[=＝]([^:：；\s]+)[:：]([^；。\n]+)/gu)) {
      const body = match[2].trim();
      const entityId = match[1].replace(/^<|>$/gu, '');
      if (body && entityId) rows.push({ entityId, text: body });
    }
  }
  return rows;
}

/** Verb -> resulting state phrase (program shortcut until the env head ships). */
const EFFECTS: Array<[string, string]> = [
  ['提开', '已被提开'], ['掀开', '已被掀开'], ['翻开', '已被翻开'],
  ['打开', '已被打开'], ['推开', '已被推开'], ['拉开', '已被拉开'],
  ['提起', '已被提起'], ['挪开', '已被挪开'], ['拖开', '已被拖开'],
  ['拖到', '已被拖开'], ['拖走', '已被拖走'], ['移开', '已被移开'],
  ['移到', '已被移开'], ['搬到', '已被搬开'], ['让出', '已被移开'],
  ['关上', '已被关上'], ['合上', '已被合上'], ['盖回', '已被盖回'],
  ['盖上', '已被盖上'], ['推到', '已被推开'], ['推走', '已被推开'],
  ['拉下', '已被拉下'], ['拉起', '已被拉起'],
  ['点亮', '已被点亮'], ['清理', '已被清理'], ['擦净', '已被擦净'],
  ['拆下', '已被拆下'], ['卸下', '已被卸下'],
];

export function environmentPhrase(text: string, label = 'achieved'): string | null {
  if (label !== 'achieved' && label !== 'partial') return null;
  for (const [verb, phrase] of EFFECTS) {
    if (!text.includes(verb)) continue;
    return label === 'achieved' ? phrase : `已被部分${phrase.slice(2)}`;
  }
  return null;
}

/** One-item physical manipulation -> state phrase; ambiguous stays null. */
export function environmentHint(
  text: string,
  itemIds: Id[],
  state: WorldState,
  destination: unknown,
  label = 'achieved',
): { entityId: Id; text: string } | null {
  if (destination) return null;
  if (itemIds.length !== 1) return null;
  const entityId = itemIds[0];
  if (!state.initial.items[entityId]) return null;
  const phrase = environmentPhrase(text, label);
  return phrase ? { entityId, text: phrase } : null;
}
