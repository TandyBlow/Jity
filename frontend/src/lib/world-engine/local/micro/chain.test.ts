import { describe, expect, it } from 'vitest';
import type { WorldState } from '../../types';
import { destinationHint, programEnvAllowed, programMoveAllowed, settledDestination } from './results';
import { environmentHint, environmentPhrase, readEnvironments } from '../semantics/settlement/fact-environments';
import { readDestinations } from './updates';

const state = {
  initial: {
    characters: { lu: { name: '路明非' }, nono: { name: '诺诺' } },
    items: { water: { name: '水壶' }, goggles: { name: '护目镜' } },
    locations: { yard: { name: '庭院' } },
  },
} as unknown as WorldState;

describe('micro results -> updates chain', () => {
  it('turns a transfer into a structured destination', () => {
    expect(destinationHint('路明非把水壶递给诺诺', state, 'lu')).toBe('water:nono');
  });
  it('turns a walk into a structured destination', () => {
    expect(destinationHint('路明非走进庭院', state, 'lu')).toBe('lu:yard');
  });
  it('declines an unregistered item', () => {
    expect(destinationHint('路明非把外套递给诺诺', state, 'lu')).toBeNull();
  });
  it('reads the hints back from the fact text', () => {
    const map = readDestinations([
      '路明非把水壶递给诺诺（达到目的）；去向=water:nono',
      '路明非走进庭院（达到目的）；去向=lu:yard/slot_wall',
    ]);
    expect(map.get('water')).toEqual({ containerId: 'nono', slotId: null });
    expect(map.get('lu')).toEqual({ containerId: 'yard', slotId: 'slot_wall' });
  });
  it('ignores facts without a hint', () => {
    expect(readDestinations(['路明非蹲在墙角（没有变化）']).size).toBe(0);
  });
  it('asserts the destination only for an achieved action', () => {
    const dest = { entityId: 'water', containerId: 'nono', slotId: null };
    expect(settledDestination('achieved', dest, () => null)).toBe('water:nono');
    expect(settledDestination('partial', dest, () => null)).toBeNull();
    expect(settledDestination('not_achieved', dest, () => null)).toBeNull();
    expect(settledDestination('blocked', dest, () => null)).toBeNull();
    expect(settledDestination('no_change', dest, () => null)).toBeNull();
  });
});

describe('environment channel', () => {
  const envState = { initial: { items: { hatch_cover: { name: '服务巷检修盖' }, curtain: { name: '帘子' } } } } as unknown as WorldState;
  it('reads a structured environment fact', () => {
    expect(readEnvironments(['路明非把盖子提开（达到目的）；环境=hatch_cover:已被提开']))
      .toEqual([{ entityId: 'hatch_cover', text: '已被提开' }]);
  });
  it('stops the text at a fact separator', () => {
    expect(readEnvironments(['a；环境=hatch_cover:已被提开；涉及=nono'])[0].text).toBe('已被提开');
  });
  it('hints a physical manipulation of an unseen item', () => {
    expect(environmentHint('我把帘子掀开。', ['curtain'], envState, null))
      .toEqual({ entityId: 'curtain', text: '已被掀开' });
    expect(environmentHint('我把帘子掀开一条缝。', ['curtain'], envState, null, 'partial'))
      .toEqual({ entityId: 'curtain', text: '已被部分掀开' });
  });
  it('declines ambiguity and mere observation', () => {
    expect(environmentHint('我把帘子掀开。', ['curtain', 'hatch_cover'], envState, null)).toBeNull();
    expect(environmentHint('我看了看帘子。', ['curtain'], envState, null)).toBeNull();
    expect(environmentHint('我把帘子掀开。', ['curtain'], envState, { entityId: 'curtain', containerId: 'box' }))
      .toEqual({ entityId: 'curtain', text: '已被掀开' });
  });
  it('declines a failed manipulation even with an env verb', () => {
    const door = {
      initial: { locations: { foyer: { name: '钟楼门厅' } }, items: { hatch_door: { name: '钟楼地下检修门' } } },
    } as unknown as WorldState;
    expect(environmentHint('我把钟楼地下检修门拉开，门闩插着，拉不开。', ['hatch_door'], door, null))
      .toBeNull();
  });
  it('keeps a partial manipulation even when the text names the blocker', () => {
    const door = {
      initial: { locations: { foyer: { name: '钟楼门厅' } }, items: { hatch_door: { name: '钟楼地下检修门' } } },
    } as unknown as WorldState;
    expect(environmentHint('我把钟楼地下检修门拉开一条缝，门闩卡住。', ['hatch_door'], door, null, 'partial'))
      .toEqual({ entityId: 'hatch_door', text: '已被部分拉开' });
  });
  it('phrases a location manipulation without an item', () => {
    expect(environmentPhrase('我把门厅的正门推开。')).toBe('已被推开');
    expect(environmentPhrase('我把门厅的正门推开一点。', 'partial')).toBe('已被部分推开');
    expect(environmentPhrase('我走进门厅。')).toBeNull();
  });
  it('does not use a location prefix as item evidence', () => {
    const gateState = {
      initial: {
        locations: { foyer: { name: '钟楼门厅' }, lane: { name: '西侧服务巷' } },
        items: { foyer_table: { name: '门厅翻倒长桌' }, hatch_cover: { name: '服务巷检修盖' } },
      },
    } as unknown as WorldState;
    expect(environmentHint('我把门厅虚掩的正门关上。', ['foyer_table'], gateState, null)).toBeNull();
    expect(environmentHint('我把服务巷检修盖提开。', ['hatch_cover'], gateState, null))
      .toEqual({ entityId: 'hatch_cover', text: '已被提开' });
  });
  it('requires the actor to be in the item room', () => {
    const local = {
      initial: {
        locations: { shed: { name: '器材棚' }, yard: { name: '庭院' } },
        items: { counter: { name: '器材领用台' } },
        characters: { lu: { name: '路明非' }, nono: { name: '诺诺' } },
      },
      items: { counter: { position: { containerId: 'shed' } } },
      characters: { lu: { position: { containerId: 'shed' } }, nono: { position: { containerId: 'yard' } } },
    } as unknown as WorldState;
    expect(environmentHint('我把领用台推到墙边。', ['counter'], local, null, 'achieved', 'lu'))
      .toEqual({ entityId: 'counter', text: '已被推开' });
    expect(environmentHint('我把领用台推到墙边。', ['counter'], local, null, 'achieved', 'nono')).toBeNull();
    const arriving = { ...local, characters: { ...local.characters, lu: { position: { containerId: 'yard' } } } } as unknown as WorldState;
    expect(environmentHint('我走进器材棚，把领用台推到墙边。', ['counter'], arriving,
      { containerId: 'shed' }, 'achieved', 'lu')).toEqual({ entityId: 'counter', text: '已被推开' });
  });
});

describe('program env gate', () => {
  const state = {
    initial: {
      locations: { shed: { name: '器材棚' }, yard: { name: '庭院' } },
      items: { counter: { name: '器材领用台' } },
      characters: { lu: { name: '路明非' } },
    },
    items: { counter: { position: { containerId: 'shed' } } },
    characters: { lu: { position: { containerId: 'shed' } } },
  } as unknown as WorldState;
  const base = { text: '我把领用台推到墙边。', itemIds: ['counter'], memberId: 'lu', state };
  it('confirms a local physical manipulation', () => {
    expect(programEnvAllowed(base)).toBe(true);
    expect(programEnvAllowed({ ...base, text: '我把遮光帘拉下一半，挡住半边窗口。' })).toBe(true);
    const arriving = { ...state, characters: { lu: { position: { containerId: 'yard' } } } } as unknown as WorldState;
    expect(programEnvAllowed({ ...base, state: arriving, actorRoom: 'shed' })).toBe(true);
  });
  it('declines a remote item, an obstruction and a non-env verb', () => {
    expect(programEnvAllowed({ ...base, text: '我把庭院里的领用台推到墙边。', state: { ...state, characters: { lu: { position: { containerId: 'yard' } } } } as unknown as WorldState })).toBe(false);
    expect(programEnvAllowed({ ...base, text: '领用台锁着，推不动。' })).toBe(false);
    expect(programEnvAllowed({ ...base, text: '我拉检修门，拉不开。' })).toBe(false);
    expect(programEnvAllowed({ ...base, text: '我查看领用台。' })).toBe(false);
  });
});

describe('program move gate', () => {
  const base = { text: '我走进庭院。', category: 'move', destination: { entityId: 'lu', containerId: 'yard' }, memberId: 'lu', protagonistId: 'lu', currentContainer: 'lane', isLocation: true };
  it('confirms a plain walk', () => {
    expect(programMoveAllowed(base)).toBe(true);
  });
  it('does not confirm an obstructed walk', () => {
    expect(programMoveAllowed({ ...base, text: '我走进庭院，但被拦住了。' })).toBe(false);
  });
  it('does not confirm a non-location destination', () => {
    expect(programMoveAllowed({ ...base, isLocation: false })).toBe(false);
  });
  it('does not confirm another actor or an already-reached room', () => {
    expect(programMoveAllowed({ ...base, memberId: 'nono' })).toBe(false);
    expect(programMoveAllowed({ ...base, currentContainer: 'yard' })).toBe(false);
  });
});
