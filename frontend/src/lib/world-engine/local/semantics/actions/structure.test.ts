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
  it('reads an item container and slot as the moved item destination', () => {
    const gear = {
      ...state,
      initial: {
        ...state.initial,
        items: {
          ...state.initial.items,
          spare_mag2: { name: '通用短枪弹匣乙' },
          jacket_lu: { name: '演习背心', slots: [{ id: 'slot_chest', label: '胸袋' }] },
          ammo_box: { name: '开盖演习弹药箱' },
        },
      },
    } as unknown as WorldState;
    const s = buildActionStructure('路明非把通用短枪弹匣乙从弹药箱里塞进演习背心的胸袋。', scene, gear, 2);
    expect(s.destination).toEqual({ entityId: 'spare_mag2', containerId: 'jacket_lu', slotId: 'slot_chest' });
  });

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
  it('matches the manipulated object before the verb, not a later route word', () => {
    const gear = {
      ...state,
      initial: {
        ...state.initial,
        items: {
          hatch_cover: { name: '服务巷检修盖' },
          hatch_door: { name: '钟楼地下检修门' },
          foyer_table: { name: '门厅翻倒长桌' },
        },
        locations: { ...state.initial.locations, foyer: { name: '钟楼门厅' } },
      },
    } as unknown as WorldState;
    const cover = buildActionStructure('我抓住检修盖的拉环把盖子提开，看见通往钟楼的地下检修通道。', scene, gear, 2);
    expect(cover.subActions[0].itemIds).toEqual(['hatch_cover']);
    const table = buildActionStructure('我把门厅的长桌推到墙边。', scene, gear, 2);
    expect(table.subActions[0].itemIds).toEqual(['foyer_table']);
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

describe('location suffixes', () => {
  it('matches 庭院 against the registered name 中央庭院', () => {
    const big = {
      initial: {
        characters: { lu: { name: '路明非' } }, items: {},
        locations: { yard: { name: '中央庭院', slots: [] } },
      },
    } as unknown as WorldState;
    const s = buildActionStructure('路明非走进庭院。', scene, big, 2);
    expect(s.subActions[0].destination?.containerId).toBe('yard');
  });
});

describe('item ownership tie-break', () => {
  const gear = {
    initial: {
      characters: { lu: { name: '路明非' }, nono: { name: '诺诺' } },
      items: { goggles_lu: { name: '路明非的护目镜' }, spare: { name: '备用护目镜' } },
      locations: { yard: { name: '庭院', slots: [] } },
    },
  } as unknown as WorldState;
  it('picks the actor-owned item when two names tie', () => {
    const s = buildActionStructure('路明非把护目镜递给诺诺。', scene, gear, 2);
    expect(s.subActions[0].itemIds).toEqual(['goggles_lu']);
    expect(s.subActions[0].destination).toEqual({ entityId: 'goggles_lu', containerId: 'nono', slotId: null });
  });
  it('still abstains when neither tied item belongs to the actor', () => {
    expect(matchItems('护目镜', [{ id: 'a', name: '甲队护目镜' }, { id: 'b', name: '乙队护目镜' }], '路明非')).toEqual([]);
  });
  it('matches across a colloquial 的 in the registered name', () => {
    const items = [{ id: 'bench', name: '倒放长椅' }, { id: 'flower', name: '南端石花槽' }];
    expect(matchItems('把庭院南端倒放的长椅拖开，让出石花槽后的通道', items)).toEqual(['bench']);
  });
});
