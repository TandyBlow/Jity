import { describe, expect, it } from 'vitest';
import type { WorldState } from '../../../types';
import { readEnvironments, resolveEntityId } from './fact-environments';

const state = {
  initial: {
    characters: { lu: { name: '路明非' } },
    items: {
      ammo_box: { name: '开盖演习弹药箱' },
      supply_counter: { name: '器材领用台' },
      goggles_lu: { name: '路明非的护目镜' },
      spare_goggles: { name: '备用护目镜' },
    },
    locations: { shed: { name: '器材棚' } },
  },
} as unknown as WorldState;

describe('environment entity ids', () => {
  it('keeps a registered id unchanged', () => {
    expect(resolveEntityId(state, 'ammo_box')).toBe('ammo_box');
  });
  it('maps an exact display name to its id', () => {
    expect(resolveEntityId(state, '器材领用台')).toBe('supply_counter');
  });
  it('maps a short unique name to its id', () => {
    expect(resolveEntityId(state, '<弹药箱>')).toBe('ammo_box');
  });
  it('keeps an ambiguous short name unresolved', () => {
    expect(resolveEntityId(state, '护目镜')).toBe('护目镜');
  });
  it('reads a model tag with a display name through the resolver', () => {
    expect(readEnvironments(['路明非把弹药箱掀开；环境=<弹药箱>:弹药已打开'], state))
      .toEqual([{ entityId: 'ammo_box', text: '弹药已打开' }]);
  });
  it('keeps the raw id when no state is passed', () => {
    expect(readEnvironments(['环境=ammo_box:已被掀开'])).toEqual([{ entityId: 'ammo_box', text: '已被掀开' }]);
  });
});
