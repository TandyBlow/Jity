import { describe, expect, it } from 'vitest';
import type { WorldState } from '../../../types';
import type { ActionScene } from './scene';
import { buildActionStructure, matchItems } from './structure';

const state = {
  initial: {
    characters: { lu: { name: '路明非' }, nono: { name: '诺诺' } },
    items: { water: { name: '休息区饮水杯' }, cup: { name: '饮水杯' } },
    locations: { yard: { name: '庭院', slots: [{ id: 'slot_pillar3', label: '第三根廊柱后' }] } },
  },
} as unknown as WorldState;

const scene = {
  actorId: 'lu', actorName: '路明非', isProtagonist: true,
  visible: [{ id: 'nono', name: '诺诺' }], absent: [],
} as unknown as ActionScene;

describe('action structure', () => {
  it('reads a walk as a destination for the actor', () => {
    const s = buildActionStructure('路明非走进庭院。', scene, state, 2);
    expect(s.category).toBe('move');
    expect(s.destination).toEqual({ entityId: 'lu', containerId: 'yard', slotId: null });
  });
  it('matches a slot label fragment', () => {
    const s = buildActionStructure('路明非走进庭院，站到第三根柱子旁。', scene, state, 2);
    expect(s.destination?.slotId).toBe('slot_pillar3');
  });
  it('keeps the named target and a registered transfer item', () => {
    const s = buildActionStructure('路明非把休息区饮水杯递给诺诺。', scene, state, 2);
    expect(s.category).toBe('assist');
    expect(s.targetIds).toEqual(['nono']);
    expect(s.itemIds).toEqual(['water']);
    expect(s.destination).toEqual({ entityId: 'water', containerId: 'nono', slotId: null });
  });
  it('does not force an alias onto a registered item', () => {
    const s = buildActionStructure('路明非把水壶递给诺诺。', scene, state, 2);
    expect(s.itemIds).toEqual([]);
    expect(s.destination).toBeNull();
  });
  it('returns no item when two candidates tie', () => {
    expect(matchItems('饮水杯', [{ id: 'water', name: '休息区饮水杯' }, { id: 'cup', name: '饮水杯' }])).toEqual([]);
  });
  it('does not pick a target from a negated action', () => {
    const s = buildActionStructure('路明非没有把休息区饮水杯递给诺诺。', scene, state, 2);
    expect(s.targetIds).toEqual([]);
  });
});

describe('compound actions', () => {
  it('splits a sequenced action into independent sub-actions', () => {
    const s = buildActionStructure('路明非把水壶推到门边，然后走进庭院。', scene, state, 2);
    expect(s.subActions).toHaveLength(2);
    expect(s.subActions[0].id).toBe('sa1');
    expect(s.subActions[1].id).toBe('sa2');
    expect(s.subActions[1].dependsOn).toEqual(['sa1']);
    expect(s.subActions[1].category).toBe('move');
    expect(s.subActions[1].destination?.containerId).toBe('yard');
    expect(s.destination).toBeNull();
  });
  it('does not split a clause whose subject is somebody else', () => {
    const s = buildActionStructure('路明非走进庭院，然后他关上门。', scene, state, 2);
    expect(s.subActions).toHaveLength(1);
  });
});
