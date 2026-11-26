import { describe, expect, it } from 'vitest';
import type { WorldState } from '../../../types';
import { matchLocation } from './fact-destinations';

const state = {
  initial: {
    locations: {
      west: { name: '西回廊' },
      east: { name: '东回廊' },
      yard: { name: '中央庭院' },
    },
  },
} as unknown as WorldState;

describe('location matching', () => {
  it('prefers a full name over a suffix match later in the text', () => {
    expect(matchLocation(state, '在西回廊等着')?.id).toBe('west');
  });
  it('refuses an ambiguous suffix', () => {
    expect(matchLocation(state, '回廊')).toBeNull();
  })
  it('accepts a unique suffix', () => {
    expect(matchLocation(state, '走进庭院')?.id).toBe('yard');
  });
  it('prefers the longer name when one location name contains another', () => {
    const nested = { initial: { locations: { tower: { name: '钟楼' }, top: { name: '钟楼顶层' } } } } as unknown as WorldState;
    expect(matchLocation(nested, '走上钟楼顶层')?.id).toBe('top');
    expect(matchLocation(nested, '走进钟楼')?.id).toBe('tower');
  });
});
