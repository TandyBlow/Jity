// @vitest-environment node
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import * as ort from 'onnxruntime-web/wasm';
import { createBertTokenizer } from './tokenizer';
import { encodePoint, type V3EncodingFile } from './v3-encoding';
import { decodeV3 } from './v3-decode';

const read = (name: string) => readFileSync(join(process.cwd(), 'public/micro', name));

describe('v3 decode', () => {
  it('reproduces the frozen probe output on the shipped int8 graphs', async () => {
    const distDir = join(process.cwd(), 'node_modules/onnxruntime-web/dist');
    ort.env.wasm.wasmPaths = `file:///${distDir.split(String.fromCharCode(92)).join('/')}/`;
    ort.env.wasm.numThreads = 1;
    const file = JSON.parse(read('v3-encoding.json').toString('utf8')) as V3EncodingFile;
    const probe = JSON.parse(read('v3-probe.json').toString('utf8')) as {
      sample: { input: string; prefix: string; onnxFixedOutput: string;
        candidates: Array<{ id: string; name: string; type: number }> };
    };
    const tokenizer = createBertTokenizer(read('minirbt-vocab.txt').toString('utf8'));
    const inverse = Object.fromEntries(Object.entries(file.typeId).map(([key, value]) => [value, key])) as Record<number, string>;
    const candidates = probe.sample.candidates.map((candidate) => ({ id: candidate.id, name: candidate.name, type: inverse[candidate.type] }));
    const tensors = encodePoint(file, tokenizer, probe.sample.input, probe.sample.prefix, candidates);
    const session = async (name: string) => ort.InferenceSession.create(new Uint8Array(read(name)), { executionProviders: ['wasm'] });
    const encoder = await session('v3-encoder-int8.onnx');
    const decoder = await session('v3-decoder-int8.onnx');
    const candidate = await session('v3-candidate-int8.onnx');
    const result = await decodeV3({ ort, encoder, decoder, candidate, file, tensors, candidates });
    expect(result.text).toBe(probe.sample.onnxFixedOutput);
  }, 120_000);
});
