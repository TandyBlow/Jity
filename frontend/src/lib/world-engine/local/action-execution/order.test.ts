import { describe, expect, it } from 'vitest';
import { buildTestWorld, withSanity } from '../semantics/actions/fixtures';
import { isFreshRoundOrder, orderSubset, roundOrder } from './order';

describe('round order (R06)', () => {
  it('freezes ascending sanity, not alphabetical id order', () => {
    const state = buildTestWorld();
    // Sanities: hero 60, ally 55, rival 70, servant 40. Alphabetical would
    // be ally, hero, rival, servant — the whole point is that it is not.
    expect(roundOrder(state)).toEqual(['servant', 'ally', 'hero', 'rival']);
    expect(roundOrder(state)).not.toEqual(Object.keys(state.characters).sort());
  });

  it('breaks ties on the stable id so a refresh reproduces the order', () => {
    let state = buildTestWorld();
    for (const id of Object.keys(state.characters)) state = withSanity(state, id, 50);
    expect(roundOrder(state)).toEqual(['ally', 'hero', 'rival', 'servant']);
    expect(roundOrder(state)).toEqual(roundOrder(state));
  });

  it('honours explicit exclusions', () => {
    const state = buildTestWorld();
    expect(roundOrder(state, { exclude: ['servant'] })).toEqual(['ally', 'hero', 'rival']);
  });

  it('orders an automatic-round subset by the same rule and rejects unknowns', () => {
    const state = buildTestWorld();
    expect(orderSubset(state, ['rival', 'servant', 'hero'])).toEqual(['servant', 'hero', 'rival']);
    expect(() => orderSubset(state, ['ghost'])).toThrow(/round_order_unknown_character/);
  });

  it('recognises a stored fresh order but not a linked one that must stay frozen', () => {
    const state = buildTestWorld();
    expect(isFreshRoundOrder(state, ['servant', 'ally', 'hero', 'rival'])).toBe(true);
    // A linked point keeps the order frozen at round start even after sanity
    // moves; that stored order must not be "corrected".
    const later = withSanity(state, 'servant', 99);
    expect(isFreshRoundOrder(later, ['servant', 'ally', 'hero', 'rival'])).toBe(false);
    expect(roundOrder(later)).toEqual(['ally', 'hero', 'rival', 'servant']);
  });
});
