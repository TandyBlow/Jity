'use client';

/** Browser probes: the fixed 96/64 5M pair and the v3 candidate pointer
 * (fixed-prefix vs past-KV decoding, encoder + decoder-step + candidate head). */
import { useEffect } from 'react';
import { createMicroRuntime } from '@/lib/world-engine/local/micro/runtime';

const SAMPLE = '事件|角色=lu；行动=目标：我把门厅长桌拖到侧墙让出楼梯口。';
const PREFIX = 'EV|actor=lu|';
const MAX_SOURCE = 96;
const MAX_TARGET = 64;
const MAX_TOKENS = 32;

type Vocab = { itos: string[]; pad: number; bos: number; eos: number; unk: number; tokenPattern: string };

type V3Candidate = { id: string; name: string; type: number; ids: number[]; mask: number[] };
type V3File = {
  maxSource: number;
  maxTarget: number;
  maxTokens: number;
  vocab: { itos: string[]; pad: number; bos: number; eos: number; unk: number; eId: number };
  sample: {
    id: string;
    input: string;
    prefix: string;
    srcIds: number[];
    srcMask: number[];
    seedIds: number[];
    candidates: V3Candidate[];
    torchOutput: string;
  };
};

const HEADS = 8;
const HEAD_DIM = 32;
const D_MODEL = 256;
const MAX_CANDIDATES = 10;
const CAND_CHARS = 11;

const round = (value: number) => Math.round(value * 100) / 100;

const stats = (values: number[]) => {
  const sorted = [...values].sort((a, b) => a - b);
  return {
    p50: sorted[Math.floor(sorted.length * 0.5)],
    p95: sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * 0.95))],
  };
};

const argmax = (data: Float32Array, offset: number, width: number) => {
  let best = 0;
  for (let index = 1; index < width; index += 1) {
    if (data[offset + index] > data[offset + best]) best = index;
  }
  return best;
};

const lastField = (text: string) => /([a-z]+)=$/.exec(text)?.[1] ?? '';

const pickCandidate = (
  candVecs: Float32Array,
  types: number[],
  present: boolean[],
  hidden: Float32Array,
  hiddenOffset: number,
  field: string,
) => {
  const wantType = field === 'item' ? 1 : field === 'loc' ? 2 : field === 'target' ? 0 : -1;
  let allowed = present.slice();
  if (wantType >= 0) allowed = allowed.map((value, index) => value && types[index] === wantType);
  if (!allowed.some(Boolean)) allowed = present.slice();
  let best = 0;
  let bestScore = -Infinity;
  for (let index = 0; index < present.length; index += 1) {
    if (!allowed[index]) continue;
    let dot = 0;
    for (let offset = 0; offset < D_MODEL; offset += 1) {
      dot += candVecs[index * D_MODEL + offset] * hidden[hiddenOffset + offset];
    }
    const score = dot / Math.sqrt(D_MODEL);
    if (score > bestScore) {
      bestScore = score;
      best = index;
    }
  }
  return best;
};

async function runV3Probe(cancelled: () => boolean): Promise<Record<string, unknown>> {
  const result: Record<string, unknown> = { ok: false };
  let runtime: ReturnType<typeof createMicroRuntime> | null = null;
  try {
    const file = await (await fetch('/micro/v3-probe.json')).json() as V3File;
    const { vocab, sample } = file;
    const ort = await import('onnxruntime-web/wasm');
    runtime = createMicroRuntime({ threads: 1 });
    const encoder = await runtime.load('/micro/v3-encoder-int8.onnx');
    const decoder = await runtime.load('/micro/v3-decoder-int8.onnx');
    const kvDecoder = await runtime.load('/micro/v3-decoder-kv-int8.onnx');
    const candidate = await runtime.load('/micro/v3-candidate-int8.onnx');
    const loadMs = runtime.stats().loadMs;
    const int64 = (values: ArrayLike<number>, shape: number[]) =>
      new ort.Tensor('int64', BigInt64Array.from(values, (value) => BigInt(value)), shape);
    const srcIds = int64(sample.srcIds, [1, file.maxSource]);
    const srcMask = int64(sample.srcMask, [1, file.maxSource]);
    const candIds = new BigInt64Array(MAX_CANDIDATES * CAND_CHARS);
    const candMask = new BigInt64Array(MAX_CANDIDATES * CAND_CHARS);
    const candTypes = new BigInt64Array(MAX_CANDIDATES);
    sample.candidates.forEach((entry, index) => {
      entry.ids.forEach((id, offset) => { candIds[index * CAND_CHARS + offset] = BigInt(id); });
      entry.mask.forEach((value, offset) => { candMask[index * CAND_CHARS + offset] = BigInt(value); });
      candTypes[index] = BigInt(entry.type);
    });
    const candOutput = await candidate.run({
      cand_ids: new ort.Tensor('int64', candIds, [1, MAX_CANDIDATES, CAND_CHARS]),
      cand_mask: new ort.Tensor('int64', candMask, [1, MAX_CANDIDATES, CAND_CHARS]),
      cand_types: new ort.Tensor('int64', candTypes, [1, MAX_CANDIDATES]),
    });
    const candVecs = candOutput.cand_vecs.data as Float32Array;
    const types = sample.candidates.map((entry) => entry.type);
    const present = sample.candidates.map((entry) => entry.mask.some(Boolean));
    const vocabSize = vocab.itos.length;
    const cacheShape = [1, HEADS, file.maxTarget, HEAD_DIM];
    const zeroCache = () => new Float32Array(HEADS * file.maxTarget * HEAD_DIM);

    const generateFixed = async () => {
      const encodeStart = performance.now();
      const memory = (await encoder.run({ input_ids: srcIds, attention_mask: srcMask })).memory;
      const encodeMs = performance.now() - encodeStart;
      const out = [vocab.bos, ...sample.seedIds];
      const text: string[] = [];
      const tokenMs: number[] = [];
      let pointer = 0;
      let generated = 0;
      const decodeStart = performance.now();
      for (let step = 0; step < file.maxTokens; step += 1) {
        generated += 1;
        const target = new BigInt64Array(file.maxTarget).fill(BigInt(vocab.pad));
        out.forEach((id, index) => { target[index] = BigInt(id); });
        const began = performance.now();
        const outputs = await decoder.run({
          memory,
          tgt: new ort.Tensor('int64', target, [1, file.maxTarget]),
          src_mask: srcMask,
        });
        tokenMs.push(performance.now() - began);
        const logits = outputs.logits.data as Float32Array;
        const hidden = outputs.hidden.data as Float32Array;
        const position = out.length - 1;
        const best = argmax(logits, position * vocabSize, vocabSize);
        if (best === vocab.eId) {
          const index = pickCandidate(candVecs, types, present, hidden, position * D_MODEL,
            lastField(text.join('')));
          text.push(sample.candidates[index]?.id ?? '<bad>');
          out.push(best);
          pointer += 1;
        } else {
          out.push(best);
          if (best === vocab.eos) break;
          text.push(vocab.itos[best]);
        }
      }
      const decodeMs = performance.now() - decodeStart;
      return { out, output: text.join(''), pointer, generated, tokenMs, encodeMs, decodeMs };
    };

    const generateKv = async () => {
      const encodeStart = performance.now();
      const memory = (await encoder.run({ input_ids: srcIds, attention_mask: srcMask })).memory;
      const encodeMs = performance.now() - encodeStart;
      const caches: Record<string, import('onnxruntime-web/wasm').Tensor> = {};
      for (let layer = 0; layer < 4; layer += 1) {
        caches[`past_k${layer}`] = new ort.Tensor('float32', zeroCache(), cacheShape);
        caches[`past_v${layer}`] = new ort.Tensor('float32', zeroCache(), cacheShape);
      }
      const valid = new BigInt64Array(file.maxTarget);
      const out = [vocab.bos, ...sample.seedIds];
      const text: string[] = [];
      const tokenMs: number[] = [];
      let pointer = 0;
      let calls = 0;
      let generated = 0;
      let logits: Float32Array | null = null;
      let hidden: Float32Array | null = null;
      const runStep = async (token: number, position: number) => {
        valid[position] = token === vocab.pad ? 0n : 1n;
        const outputs = await kvDecoder.run({
          token: int64([token], [1, 1]),
          step: int64([position], [1]),
          valid: new ort.Tensor('int64', BigInt64Array.from(valid), [1, file.maxTarget]),
          memory,
          src_mask: srcMask,
          ...caches,
        });
        for (let layer = 0; layer < 4; layer += 1) {
          caches[`past_k${layer}`] = outputs[`new_k${layer}`];
          caches[`past_v${layer}`] = outputs[`new_v${layer}`];
        }
        calls += 1;
        return outputs;
      };
      const prefillStart = performance.now();
      for (let index = 0; index < out.length; index += 1) {
        const outputs = await runStep(out[index], index);
        logits = outputs.logits.data as Float32Array;
        hidden = outputs.hidden.data as Float32Array;
      }
      const prefillMs = performance.now() - prefillStart;
      const decodeStart = performance.now();
      for (let step = 0; step < file.maxTokens && logits && hidden; step += 1) {
        generated += 1;
        const best = argmax(logits, 0, vocabSize);
        if (best === vocab.eId) {
          const index = pickCandidate(candVecs, types, present, hidden, 0, lastField(text.join('')));
          text.push(sample.candidates[index]?.id ?? '<bad>');
          out.push(best);
          pointer += 1;
        } else {
          out.push(best);
          if (best === vocab.eos) break;
          text.push(vocab.itos[best]);
        }
        const began = performance.now();
        const outputs = await runStep(best, out.length - 1);
        tokenMs.push(performance.now() - began);
        logits = outputs.logits.data as Float32Array;
        hidden = outputs.hidden.data as Float32Array;
      }
      const decodeMs = performance.now() - decodeStart;
      return { out, output: text.join(''), pointer, generated, tokenMs, encodeMs, decodeMs, prefillMs, calls };
    };

    if (cancelled()) throw new Error('cancelled');
    const fixedRuns = [];
    const kvRuns = [];
    for (let index = 0; index < 5; index += 1) {
      const started = performance.now();
      const run = await generateFixed();
      fixedRuns.push({ ...run, fullMs: performance.now() - started });
      const kvStarted = performance.now();
      const kvRun = await generateKv();
      kvRuns.push({ ...kvRun, fullMs: performance.now() - kvStarted });
    }
    const fixedFull = stats(fixedRuns.map((run) => run.fullMs));
    const fixedDecode = stats(fixedRuns.map((run) => run.decodeMs));
    const kvFull = stats(kvRuns.map((run) => run.fullMs));
    const kvDecode = stats(kvRuns.map((run) => run.decodeMs));
    const fixed = fixedRuns[0];
    const kv = kvRuns[0];
    const mean = (values: number[]) => values.reduce((sum, value) => sum + value, 0) / values.length;
    result.ok = true;
    result.loadMs = Math.round(loadMs);
    result.sampleId = sample.id;
    result.sampleInput = sample.input;
    result.samplePrefix = sample.prefix;
    result.expected = sample.torchOutput;
    result.vocabSize = vocabSize;
    result.fixed = {
      output: fixed.output,
      tokens: fixed.generated,
      pointerSelections: fixed.pointer,
      encodeMs: round(stats(fixedRuns.map((run) => run.encodeMs)).p50),
      perTokenMs: round(mean(fixed.tokenMs)),
      decodeP50Ms: round(fixedDecode.p50),
      decodeP95Ms: round(fixedDecode.p95),
      fullP50Ms: round(fixedFull.p50),
      fullP95Ms: round(fixedFull.p95),
      runs: fixedRuns.map((run) => ({
        fullMs: round(run.fullMs),
        decodeMs: round(run.decodeMs),
        tokens: run.generated,
      })),
    };
    result.kv = {
      output: kv.output,
      tokens: kv.generated,
      pointerSelections: kv.pointer,
      encodeMs: round(stats(kvRuns.map((run) => run.encodeMs)).p50),
      perTokenMs: round(mean(kv.tokenMs)),
      prefillMs: round(kv.prefillMs),
      calls: kv.calls,
      decodeP50Ms: round(kvDecode.p50),
      decodeP95Ms: round(kvDecode.p95),
      fullP50Ms: round(kvFull.p50),
      fullP95Ms: round(kvFull.p95),
      runs: kvRuns.map((run) => ({
        fullMs: round(run.fullMs),
        decodeMs: round(run.decodeMs),
        tokens: run.generated,
      })),
    };
    result.sameTokens = fixed.out.join(',') === kv.out.join(',');
    result.sameOutput = fixed.output === kv.output;
    result.benefit = {
      perToken: round(mean(fixed.tokenMs) / mean(kv.tokenMs)),
      decode: round(fixedDecode.p50 / kvDecode.p50),
      full: round(fixedFull.p50 / kvFull.p50),
    };
  } catch (error) {
    result.error = String(error instanceof Error ? error.stack ?? error.message : error);
  } finally {
    await runtime?.dispose();
  }
  return result;
}

export default function MicroSeq2SeqProbePage() {
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const result: Record<string, unknown> = { ok: false };
      try {
        const vocab = await (await fetch('/micro/probe-vocab.json')).json() as Vocab;
        const stoi = new Map(vocab.itos.map((token, index) => [token, index]));
        const regex = new RegExp(vocab.tokenPattern, 'g');
        const tokens = (text: string) => Array.from(text.matchAll(regex), (match) => match[0]);
        const encode = (text: string, maxLen: number) => {
          const ids = tokens(text).slice(0, maxLen - 2).map((token) => stoi.get(token) ?? vocab.unk);
          return [vocab.bos, ...ids, vocab.eos];
        };
        const ort = await import('onnxruntime-web/wasm');
        const runtime = createMicroRuntime({ threads: 1 });
        const encoder = await runtime.load('/micro/probe-encoder-int8.onnx');
        const decoder = await runtime.load('/micro/probe-decoder-int8.onnx');
        const srcIds = encode(SAMPLE, MAX_SOURCE);
        const source = new BigInt64Array(MAX_SOURCE).fill(BigInt(vocab.pad));
        srcIds.forEach((id, index) => { source[index] = BigInt(id); });
        const mask = new BigInt64Array(MAX_SOURCE);
        for (let index = 0; index < MAX_SOURCE; index += 1) mask[index] = source[index] === BigInt(vocab.pad) ? 0n : 1n;
        const srcTensor = new ort.Tensor('int64', source, [1, MAX_SOURCE]);
        const maskTensor = new ort.Tensor('int64', mask, [1, MAX_SOURCE]);
        const runOnce = async () => {
          const encodeStart = performance.now();
          const memory = (await encoder.run({ src: srcTensor })).memory;
          const encodeMs = performance.now() - encodeStart;
          const seed = tokens(PREFIX).slice(-30).map((token) => stoi.get(token) ?? vocab.unk);
          const out = [vocab.bos, ...seed];
          const tokenMs: number[] = [];
          for (let step = 0; step < MAX_TOKENS; step += 1) {
            const target = new BigInt64Array(MAX_TARGET).fill(BigInt(vocab.pad));
            out.slice(-MAX_TARGET).forEach((id, index) => { target[index] = BigInt(id); });
            const targetTensor = new ort.Tensor('int64', target, [1, MAX_TARGET]);
            const start = performance.now();
            const logits = (await decoder.run({ memory, tgt: targetTensor, src_mask: maskTensor })).logits;
            tokenMs.push(performance.now() - start);
            const data = logits.data as Float32Array;
            const width = vocab.itos.length;
            const offset = (out.length - 1) * width;
            let best = 0;
            for (let index = 1; index < width; index += 1) {
              if (data[offset + index] > data[offset + best]) best = index;
            }
            out.push(best);
            if (best === vocab.eos) break;
          }
          const continuation = out.slice(1 + seed.length)
            .filter((id) => id !== vocab.pad && id !== vocab.bos && id !== vocab.eos)
            .map((id) => vocab.itos[id]).join('');
          return { continuation, encodeMs, tokenMs };
        };
        const runs = [];
        for (let index = 0; index < 5; index += 1) {
          const start = performance.now();
          const run = await runOnce();
          runs.push({ ...run, fullMs: performance.now() - start });
        }
        const full = runs.map((run) => run.fullMs).sort((a, b) => a - b);
        const p50 = full[Math.floor(full.length * 0.5)];
        const p95 = full[Math.min(full.length - 1, Math.floor(full.length * 0.95))];
        result.ok = true;
        result.loadMs = Math.round(runtime.stats().loadMs);
        result.sampleInput = SAMPLE;
        result.samplePrefix = PREFIX;
        result.output = runs[0].continuation;
        result.tokens = runs[0].tokenMs.length;
        result.encodeMs = Math.round(runs[0].encodeMs * 100) / 100;
        result.perTokenMs = Math.round((runs[0].tokenMs.reduce((a, b) => a + b, 0) / runs[0].tokenMs.length) * 100) / 100;
        result.fullP50Ms = Math.round(p50 * 100) / 100;
        result.fullP95Ms = Math.round(p95 * 100) / 100;
        result.runs = runs.map((run) => ({ fullMs: Math.round(run.fullMs * 100) / 100, tokens: run.tokenMs.length }));
        await runtime.dispose();
      } catch (error) {
        result.error = String(error instanceof Error ? error.stack ?? error.message : error);
      }
      if (!cancelled) (window as unknown as { __probeResult?: unknown }).__probeResult = result;
      if (cancelled) return;
      const v3 = await runV3Probe(() => cancelled);
      if (!cancelled) (window as unknown as { __v3ProbeResult?: unknown }).__v3ProbeResult = v3;
    })();
    return () => { cancelled = true; };
  }, []);
  return <main style={{ padding: 24, fontFamily: 'monospace' }}>seq2seq probe running…</main>;
}
