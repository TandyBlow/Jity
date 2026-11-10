/** Byte-for-byte parity checks for `world-canonical-v1`. The expected bytes
 * and SHA-256 values are produced by the pinned Python canonical encoder in
 * `build-kernel-fixtures.py`. */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { canonicalBytes, canonicalDigest, canonicalJson } from './canonical';

const fixture = JSON.parse(readFileSync(
  resolve('scripts/parallel-kernel/fixtures/kernel-differential.json'), 'utf8'));

describe('world-canonical-v1', () => {
  for (const [index, sample] of fixture.canonical.entries()) {
    it(`matches Python bytes and digest for sample ${index}`, async () => {
      expect(canonicalJson(sample.value)).toBe(sample.canonical);
      expect(await canonicalDigest(sample.value)).toBe(sample.sha256);
      expect(new TextDecoder().decode(canonicalBytes(sample.value))).toBe(sample.canonical);
    });
  }

  it('sorts keys and preserves non-ASCII values as UTF-8', () => {
    expect(canonicalJson({ z: '中文', a: '😀' })).toBe('{"a":"😀","z":"中文"}');
  });

  it('escapes only quotes, backslashes and control characters', () => {
    expect(canonicalJson('a"b\\c\u0000\u001f\n')).toBe('"a\\"b\\\\c\\u0000\\u001f\\u000a"');
  });

  it('accepts ASCII control characters in object keys, like Python isascii()', () => {
    expect(canonicalJson({ '\u0001': 1 })).toBe('{"\\u0001":1}');
  });

  it('rejects non-ASCII object keys', () => {
    expect(() => canonicalJson({ 中文: 1 })).toThrow('ASCII');
  });

  it('rejects an unpaired surrogate in a value', () => {
    expect(() => canonicalJson('a\uD800')).toThrow('surrogate');
  });

  it('rejects an unpaired surrogate in a key', () => {
    expect(() => canonicalJson({ '\uD800': 1 })).toThrow('surrogate');
  });

  it('rejects fractions, non-finite values and integers outside the safe range', () => {
    expect(() => canonicalJson(1.5)).toThrow('safe integer');
    expect(() => canonicalJson(Number.NaN)).toThrow('safe integer');
    expect(() => canonicalJson(Number.POSITIVE_INFINITY)).toThrow('safe integer');
    expect(() => canonicalJson(2 ** 53)).toThrow('safe integer');
  });

  it('accepts both bounds of the safe-integer range', () => {
    expect(canonicalJson([0, -0, 9007199254740991, -9007199254740991]))
      .toBe('[0,0,9007199254740991,-9007199254740991]');
  });
});
