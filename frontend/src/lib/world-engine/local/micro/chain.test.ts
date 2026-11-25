import { describe, expect, it } from 'vitest';
import type { WorldState } from '../../types';
import { destinationHint, programMoveAllowed, settledDestination } from './results';
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
