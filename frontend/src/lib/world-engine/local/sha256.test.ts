import { describe, expect, it } from 'vitest';
import { sha256Hex, sha256HexJs } from './sha256';

describe('sha256 fallback', () => {
  it('matches the standard vectors', () => {
    const utf8 = (text: string) => new TextEncoder().encode(text);
    expect(sha256HexJs(utf8(''))).toBe('e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855');
    expect(sha256HexJs(utf8('abc'))).toBe('ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad');
    expect(sha256HexJs(utf8('abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq')))
      .toBe('248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1');
  });
  it('agrees with crypto.subtle when available', async () => {
    const bytes = new TextEncoder().encode('自由一日 · 医护白线禁射 · 15:45 停赛');
    expect(sha256HexJs(bytes)).toBe(await sha256Hex(bytes));
  });
});
