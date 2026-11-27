import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { createBertTokenizer } from './tokenizer';
import { encodePoint, type V3EncodingFile } from './v3-encoding';

const read = (name: string) => readFileSync(join(process.cwd(), 'public/micro', name), 'utf8');

describe('v3 encoder', () => {
  it('reproduces the exported probe tensors exactly', () => {
    const file = JSON.parse(read('v3-encoding.json')) as V3EncodingFile;
    const probe = JSON.parse(read('v3-probe.json')) as {
      sample: {
        input: string; prefix: string;
        srcIds: number[]; srcMask: number[]; seedIds: number[];
        candidates: Array<{ id: string; name: string; type: number; ids: number[]; mask: number[] }>;
      };
    };
    const tokenizer = createBertTokenizer(read('minirbt-vocab.txt'));
    const sample = probe.sample;
    const inverse = Object.fromEntries(Object.entries(file.typeId).map(([key, value]) => [value, key]));
    const tensors = encodePoint(file, tokenizer, sample.input, sample.prefix,
      sample.candidates.map((candidate) => ({ id: candidate.id, name: candidate.name, type: inverse[candidate.type] })));
    expect(tensors.srcIds).toEqual(sample.srcIds);
    expect(tensors.srcMask).toEqual(sample.srcMask);
    expect(tensors.seedIds).toEqual(sample.seedIds);
    const { maxCandidates, candChars } = file.constants;
    const ids = new Array<number>(maxCandidates * candChars).fill(file.cand.pad);
    const mask = new Array<number>(maxCandidates * candChars).fill(0);
    sample.candidates.forEach((candidate, index) => {
      candidate.ids.forEach((id, offset) => { ids[index * candChars + offset] = id; });
      candidate.mask.forEach((value, offset) => { mask[index * candChars + offset] = value; });
    });
    expect(tensors.candIds).toEqual(ids);
    expect(tensors.candMask).toEqual(mask);
    expect(tensors.candTypes.slice(0, sample.candidates.length)).toEqual(sample.candidates.map((candidate) => candidate.type));
  });
});
