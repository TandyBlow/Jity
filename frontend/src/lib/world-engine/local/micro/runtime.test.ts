import { describe, expect, it } from 'vitest';
import { packBatch } from './runtime';

describe('micro batch packing', () => {
  it('pads rows to the longest length and masks the padding', () => {
    const packed = packBatch([[1, 2, 3], [4]]);
    expect(packed).toMatchObject({ width: 3, batch: 2 });
    expect([...packed.ids]).toEqual([1n, 2n, 3n, 4n, 0n, 0n]);
    expect([...packed.mask]).toEqual([1n, 1n, 1n, 1n, 0n, 0n]);
  });

  it('keeps an empty batch empty', () => {
    expect(packBatch([])).toMatchObject({ width: 1, batch: 0 });
  });
});
