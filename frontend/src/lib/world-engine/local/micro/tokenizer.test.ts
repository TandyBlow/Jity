import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { createBertTokenizer } from './tokenizer';

const vocabPath = fileURLToPath(new URL('../../../../../public/micro/minirbt-vocab.txt', import.meta.url));
const fixturePath = fileURLToPath(new URL('./tokenizer-fixture.json', import.meta.url));
const tok = createBertTokenizer(readFileSync(vocabPath, 'utf8'));
const fixture = JSON.parse(readFileSync(fixturePath, 'utf8')) as {
  cases: Array<{ text: string; ids: number[] }>;
  pairs: Array<{ a: string; b: string; ids: number[] }>;
};

describe('browser tokenizer parity with transformers BertTokenizer', () => {
  for (const item of fixture.cases) {
    it(`encodes ${JSON.stringify(item.text).slice(0, 40)}`, () => {
      expect(tok.encode(item.text, 128)).toEqual(item.ids);
    });
  }
  for (const item of fixture.pairs) {
    it(`encodes the pair ${item.a.slice(0, 20)} / ${item.b}`, () => {
      expect(tok.encodePair(item.a, item.b, 128).ids).toEqual(item.ids);
    });
  }
  it('keeps [CLS]/[SEP] and the vocab size', () => {
    expect(tok.vocabSize).toBe(21128);
    const ids = tok.encode('路明非');
    expect(ids[0]).toBe(101);
    expect(ids[ids.length - 1]).toBe(102);
  });
});
