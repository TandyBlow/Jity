import { readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { renderNarrationInput } from './pipeline';
import { YUYAN_700M_CHARSET } from './tokenizer';
import { normalizeProjection } from './normalize';
import { NarrationInputError } from './types';

interface VectorCase {
  caseId: string;
  kind: 'real' | 'synthetic' | 'negative';
  rawProjection?: unknown;
  projection: unknown;
  normalization: { path: string; action: string; removed: string[]; before: string; after: string }[];
  expected: {
    status: 'ok' | 'error';
    text?: string;
    sha256?: string;
    bytesUtf8Hex?: string;
    segments?: unknown[];
    resultFills?: unknown[];
    stage?: string;
    errorCode?: string;
    errorPath?: string;
  };
}

const root = resolve('src/lib/world-engine/local/narration-input/goldens/runtime-v2');
const vectors = readFileSync(join(root, 'vectors.jsonl'), 'utf8').split('\n').filter(Boolean)
  .map((line) => JSON.parse(line) as VectorCase);
const manifest = JSON.parse(readFileSync(join(root, 'golden-manifest.json'), 'utf8')) as {
  cases: number;
  files: { 'vectors.jsonl': { sha256: string } };
  versions: Record<string, string>;
  tokenizer: { sha256: string; vocabSize: number };
};

describe('lane-10 v2 golden vectors', () => {
  it('freezes the same 49 cases and versions lane 10 published', () => {
    expect(vectors).toHaveLength(49);
    expect(manifest.cases).toBe(49);
    expect(manifest.versions.serializerVersion).toBe('yuyan-prose-result-v2');
    expect(manifest.versions.projectionVersion).toBe('narration-result-view-v2');
    expect(manifest.tokenizer.sha256).toBe('20287a9d1a2ec9d82b2a13f02c10c7b81e8bb015f114134bca6b06e5c8d376b4');
    expect(vectors.map((entry) => entry.kind).filter((kind) => kind === 'real')).toHaveLength(20);
  });

  for (const vector of vectors) {
    it(`${vector.caseId} matches the reference bytes, segments and errors`, () => {
      const raw = vector.rawProjection ?? vector.projection;
      const expected = vector.expected;
      if (expected.status === 'ok') {
        // `synthetic-non-bmp-sort` deliberately uses a non-BMP name outside
        // the YuYan vocabulary to test code-point ordering; the reference ran
        // it without the tokenizer stage. Any other ok vector must tokenize.
        const tokenizable = Array.from(expected.text ?? '').every((char) => YUYAN_700M_CHARSET.has(char));
        const rendered = renderNarrationInput(raw, { checkTokenizer: tokenizable });
        expect(rendered.text).toBe(expected.text);
        expect(rendered.sha256).toBe(expected.sha256);
        expect(rendered.bytesUtf8Hex).toBe(expected.bytesUtf8Hex);
        expect(rendered.segments).toEqual(expected.segments);
        expect(rendered.resultFills).toEqual(expected.resultFills ?? []);
        if (vector.rawProjection) {
          expect(rendered.normalization).toEqual(vector.normalization);
        }
        expect(rendered.serializerVersion).toBe('yuyan-prose-result-v2');
        expect(rendered.version.tokenizerHash).toBe(manifest.tokenizer.sha256);
        return;
      }
      const options = { checkTokenizer: true, skipBuild: expected.stage === 'serialize' };
      try {
        renderNarrationInput(raw, options);
      } catch (error) {
        expect(error).toBeInstanceOf(NarrationInputError);
        const failure = error as NarrationInputError;
        expect(failure.code, `${vector.caseId} code`).toBe(expected.errorCode);
        expect(failure.path, `${vector.caseId} path`).toBe(expected.errorPath);
        expect(failure.stage, `${vector.caseId} stage`).toBe(expected.stage);
        return;
      }
      throw new Error(`${vector.caseId}: expected ${expected.stage}/${expected.errorCode}`);
    });
  }

  it('keeps the normalization ledger for the real rows', () => {
    const real = vectors.find((entry) => entry.caseId === 'real-row-0002')!;
    expect(real.normalization[0]).toMatchObject({
      path: '本回合变化/时间推进',
      before: '2 分钟',
      after: '2分钟',
    });
    // The frozen projection is already normalized; re-normalizing it is a
    // no-op, and the ledger is not invented again.
    const { ledger } = normalizeProjection(real.projection);
    expect(ledger).toEqual([]);
  });
});
