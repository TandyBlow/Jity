import { createHash } from 'node:crypto';
import { existsSync, readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import {
  YUYAN_700M_CHARSET, YUYAN_CHARSET_SOURCE_SHA256, YUYAN_CHARSET_VERSION, assertEncodable,
} from './charset';
import { NarrationInputError } from './types';

const vocabPath = process.env.YUYAN_VOCAB_PATH ?? 'D:/others/Jity/.local/yuyan/_vocab.json';

describe('YuYan charset', () => {
  it('records the source identity and the characters the format needs', () => {
    expect(YUYAN_CHARSET_VERSION).toBe('yuyan-700m-charset-v1');
    expect(YUYAN_CHARSET_SOURCE_SHA256).toBe('c67c92370d90be7960e53b96dde940d334d5100d3d642478f2be0d2ebe5ac237');
    for (const char of ['【', '】', '※', '，', '。', '、', '；', '：', '《', '》', '阿', 'Z']) {
      expect(YUYAN_700M_CHARSET.has(char), char).toBe(true);
    }
    for (const char of [' ', '\t', '\n', '\r', '\u3000', '🚀']) {
      expect(YUYAN_700M_CHARSET.has(char), JSON.stringify(char)).toBe(false);
    }
  });

  it('rejects whitespace and OOV with stable error categories', () => {
    for (const [text, code] of [['a b', 'whitespace'], ['a\nb', 'whitespace'], ['a🚀', 'oov']] as const) {
      try {
        assertEncodable(text);
        throw new Error('expected rejection');
      } catch (error) {
        expect(error).toBeInstanceOf(NarrationInputError);
        expect((error as NarrationInputError).code).toBe(code);
      }
    }
  });

  it('can disable the vocabulary check for a different tokenizer without disabling whitespace', () => {
    expect(() => assertEncodable('a🚀', { charset: null })).not.toThrow();
    expect(() => assertEncodable('a b', { charset: null })).toThrowError(NarrationInputError);
  });

  it.skipIf(!existsSync(vocabPath))('matches the live vocab file from which it was derived', () => {
    const raw = readFileSync(vocabPath);
    const hash = createHash('sha256').update(raw).digest('hex');
    expect(hash).toBe(YUYAN_CHARSET_SOURCE_SHA256);
    const vocab = JSON.parse(raw.toString('utf8')) as string[];
    const single = new Set(vocab.filter((symbol) => Array.from(symbol).length === 1));
    expect(single.size).toBe(YUYAN_700M_CHARSET.size);
    for (const char of single) expect(YUYAN_700M_CHARSET.has(char), char).toBe(true);
  });
});
