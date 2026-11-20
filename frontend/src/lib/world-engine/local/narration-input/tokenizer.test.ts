import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { YUYAN_700M_CHARSET, YUYAN_TOKENIZER } from './tokenizer';
import { TOKENIZER_SHA256, TOKENIZER_VOCAB_SIZE } from './versions';

describe('YuYan tokenizer binding', () => {
  it('binds the committed vocabulary file, not just a declared hash', () => {
    const path = resolve('src/lib/world-engine/local/narration-input/tokenizer/yuyan-v1/dict.txt');
    const bytes = readFileSync(path);
    expect(createHash('sha256').update(bytes).digest('hex')).toBe(TOKENIZER_SHA256);
    const entries = new Set(bytes.toString('utf8').split('\n').filter(Boolean).map((line) => line.split(' ')[0]));
    expect(entries.size).toBe(TOKENIZER_VOCAB_SIZE);
    const single = new Set([...entries].filter((entry) => Array.from(entry).length === 1));
    expect(single.size).toBe(YUYAN_700M_CHARSET.size);
    for (const char of single) expect(YUYAN_700M_CHARSET.has(char), char).toBe(true);
    expect(YUYAN_TOKENIZER.sha256).toBe(TOKENIZER_SHA256);
  });
});
