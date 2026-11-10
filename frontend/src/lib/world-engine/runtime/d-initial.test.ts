import { expect, test } from 'vitest';
import { generateDInitial } from './d-initial';
import type { Json } from '../types';
const options = { brief: '钥匙争夺', locations: 1, items: 0, characters: 1, tasksPerCharacter: 1,
  initialTime: { calendar: 'gregorian' as const, dateTime: '2026-01-01T00:00:00', instantOrdinal: 0 } };
test('D01 allocates IDs before batches and checks graph/task ownership', async () => {
  let next = 0;
  const calls: Json[] = [];
  const draft = await generateDInitial(async (_, input): Promise<Json> => {
    calls.push(input);
    if (calls.length === 1) return { id1: { id: 'id1', name: '屋', parentLocationId: null, initialAppearance: '小屋' } };
    if (calls.length === 2) return {};
    return { id2: { id: 'id2', name: '田', initialPosition: { containerId: 'id1' }, initialAppearance: '外套', initialPersonality: '谨慎', initialSanity: 10,
      tasks: { id3: { id: 'id3', ownerId: 'id2', parentTaskId: null, goal: '找到钥匙', status: 'pending' } } } };
  }, { ...options, allocate: () => `id${++next}` });
  expect(calls).toHaveLength(3);
  expect(draft).toMatchObject({ protagonistId: 'id2', locations: { id1: { id: 'id1' } } });
});
test('D01 cannot accept API-created identities', async () => {
  await expect(generateDInitial(async () => ({ invented: {} }), { ...options, allocate: (() => { let i=0; return () => `id${++i}`; })() })).rejects.toThrow('coverage');
});
