import { describe, expect, it } from 'vitest';
import type { WorldState } from '../../types';
import { buildRoundEvents, classifyRepeat, eventLines, normalizeEventText } from './events';

function state(): WorldState {
  const initial = {
    engineVersion: 'world-engine-v1' as const,
    schemaVersion: 1 as const,
    protagonistId: 'lu',
    initialTime: { calendar: 'gregorian' as const, dateTime: '2026-11-25T10:00:00', instantOrdinal: 0 },
    locations: {
      yard: { id: 'yard', name: '中央庭院', parentLocationId: null, initialAppearance: '' },
      lane: { id: 'lane', name: '西侧服务巷', parentLocationId: null, initialAppearance: '' },
    },
    items: {
      goggles: { id: 'goggles', name: '护目镜', initialPosition: { containerId: 'lu' }, initialAppearance: '' },
    },
    characters: {
      lu: {
        id: 'lu', name: '路明非', initialPosition: { containerId: 'lane' }, initialAppearance: '',
        initialPersonality: '谨慎', initialSanity: 50,
        tasks: { task_1: { id: 'task_1', ownerId: 'lu', parentTaskId: null, goal: '确认地图', status: 'pending' as const } },
      },
      tang: {
        id: 'tang', name: '唐骁', initialPosition: { containerId: 'lane' }, initialAppearance: '',
        initialPersonality: '果断', initialSanity: 50, tasks: {},
      },
    },
  };
  return {
    engineVersion: 'world-engine-v1', schemaVersion: 1, worldId: 'w', protagonistId: 'lu',
    time: { calendar: 'gregorian', dateTime: '2026-11-25T10:00:00', instantOrdinal: 0 }, initial: { ...initial, worldId: 'w' },
    locations: { yard: { id: 'yard', appearanceChanges: [] }, lane: { id: 'lane', appearanceChanges: [] } },
    items: { goggles: { id: 'goggles', appearanceChanges: [], position: { containerId: 'lu' } } },
    characters: {
      lu: { id: 'lu', appearanceChanges: [], position: { containerId: 'lane' }, personalityChanges: [], sanity: 50, tasks: structuredClone(initial.characters.lu.tasks) },
      tang: { id: 'tang', appearanceChanges: [], position: { containerId: 'lane' }, personalityChanges: [], sanity: 50, tasks: {} },
    },
  };
}

describe('continuation events', () => {
  it('turns committed deltas into move and task events', () => {
    const events = buildRoundEvents([{
      pointId: 'p1',
      timeAdvance: null,
      entityDeltas: {
        lu: { entityId: 'lu', positionSet: { containerId: 'yard' }, tasksAchieved: ['task_1'] },
      },
    }], state(), 'digest_1');
    expect(events.map((row) => row.kind)).toEqual(['move', 'task']);
    expect(events[0].text).toContain('中央庭院');
    expect(events.every((row) => row.worldDigest === 'digest_1')).toBe(true);
  });

  it('classifies same text as new, same-world repeat or new-world repeat', () => {
    const candidate = { characterId: 'tang', text: '唐骁守住西侧服务巷。' };
    expect(classifyRepeat(candidate, [], 'd2')).toBe('new');
    expect(classifyRepeat(candidate, [
      { characterId: 'tang', text: '唐骁守住西侧服务巷', worldDigest: 'd1' },
    ], 'd1')).toBe('same_world');
    expect(classifyRepeat(candidate, [
      { characterId: 'tang', text: '唐骁守住西侧服务巷', worldDigest: 'd1' },
    ], 'd2')).toBe('new_world');
    expect(classifyRepeat(candidate, [
      { characterId: 'nono', text: '唐骁守住西侧服务巷', worldDigest: 'd1' },
    ], 'd1')).toBe('new');
  });

  it('keeps event lines unique and bounded', () => {
    const lines = eventLines([
      { pointId: 'p1', kind: 'move', entityId: 'lu', containerId: 'yard', slotId: null, taskIds: [], text: '路明非移动到中央庭院' },
      { pointId: 'p2', kind: 'move', entityId: 'lu', containerId: 'yard', slotId: null, taskIds: [], text: '路明非移动到中央庭院' },
      { pointId: 'p3', kind: 'sanity', entityId: 'lu', containerId: null, slotId: null, taskIds: [], text: '路明非理智变为48' },
    ], 1);
    expect(lines).toEqual(['p3：路明非理智变为48']);
  });

  it('normalizes trailing punctuation for identity', () => {
    expect(normalizeEventText(' 唐骁守住巷口。 ')).toBe('唐骁守住巷口');
  });
});
