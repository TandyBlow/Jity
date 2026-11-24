import { describe, expect, it } from 'vitest';
import type { WorldState } from '../../types';
import { destinationHint } from './results';
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
});
