/** Greedy decode for the v3 candidate-pointer model (fixed-prefix decoder).
 *
 * Mirrors `decode_fixed_np` in the exporter: the decoder sees the full target
 * prefix each step; when it emits `<e>`, a dot-product head picks among the
 * encoded candidate entities (typed by the field before it). The caller owns
 * the ORT sessions so the page can share them with other ports. */
import type { V3EncodingFile, V3Tensors, V3CandidateInput } from './v3-encoding';

type Ort = typeof import('onnxruntime-web/wasm');

export interface V3DecodeInput {
  ort: Ort;
  encoder: import('onnxruntime-web/wasm').InferenceSession;
  decoder: import('onnxruntime-web/wasm').InferenceSession;
  candidate: import('onnxruntime-web/wasm').InferenceSession;
  file: V3EncodingFile;
  tensors: V3Tensors;
  candidates: V3CandidateInput[];
  maxTokens?: number;
}

function argmax(data: Float32Array, offset: number, width: number): number {
  let best = 0;
  for (let index = 1; index < width; index += 1) {
    if (data[offset + index] > data[offset + best]) best = index;
  }
  return best;
}

function lastField(text: string): string {
  return /([a-z]+)=$/.exec(text)?.[1] ?? '';
}

function pickCandidate(candVecs: Float32Array, types: number[], present: boolean[],
  hidden: Float32Array, hiddenOffset: number, field: string, dModel: number): number {
  const wantType = field === 'item' ? 1 : field === 'loc' ? 2 : field === 'target' ? 0 : -1;
  let allowed = present.slice();
  if (wantType >= 0) allowed = allowed.map((value, index) => value && types[index] === wantType);
  if (!allowed.some(Boolean)) allowed = present.slice();
  let best = 0;
  let bestScore = -Infinity;
  for (let index = 0; index < present.length; index += 1) {
    if (!allowed[index]) continue;
    let dot = 0;
    for (let offset = 0; offset < dModel; offset += 1) {
      dot += candVecs[index * dModel + offset] * hidden[hiddenOffset + offset];
    }
    const score = dot / Math.sqrt(dModel);
    if (score > bestScore) {
      bestScore = score;
      best = index;
    }
  }
  return best;
}

export async function decodeV3(input: V3DecodeInput): Promise<{ text: string; eId: number; tokens: number[] }> {
  const { ort, encoder, decoder, candidate, file, tensors, candidates } = input;
  const { maxSource, maxTarget, maxTokens, maxCandidates, candChars, dModel } = file.constants;
  const limit = input.maxTokens ?? maxTokens;
  const int64 = (values: ArrayLike<number>, shape: number[]) =>
    new ort.Tensor('int64', BigInt64Array.from(values, (value) => BigInt(value)), shape);
  const candOutput = await candidate.run({
    cand_ids: int64(tensors.candIds, [1, maxCandidates, candChars]),
    cand_mask: int64(tensors.candMask, [1, maxCandidates, candChars]),
    cand_types: int64(tensors.candTypes, [1, maxCandidates]),
  });
  const candVecs = candOutput.cand_vecs.data as Float32Array;
  const types = tensors.candTypes.slice(0, candidates.length);
  const present = candidates.map((_, index) => tensors.candMask.slice(index * candChars, (index + 1) * candChars).some(Boolean));
  const srcIds = int64(tensors.srcIds, [1, maxSource]);
  const srcMask = int64(tensors.srcMask, [1, maxSource]);
  const memory = (await encoder.run({ input_ids: srcIds, attention_mask: srcMask })).memory;
  const eId = file.out.stoi['<e>'] ?? -1;
  const vocabSize = file.out.itos.length;
  const out = [file.out.bos, ...tensors.seedIds];
  const text: string[] = [];
  for (let step = 0; step < limit; step += 1) {
    const target = new BigInt64Array(maxTarget).fill(BigInt(file.out.pad));
    out.forEach((id, index) => { target[index] = BigInt(id); });
    const outputs = await decoder.run({ memory, tgt: new ort.Tensor('int64', target, [1, maxTarget]), src_mask: srcMask });
    const logits = outputs.logits.data as Float32Array;
    const hidden = outputs.hidden.data as Float32Array;
    const position = out.length - 1;
    const best = argmax(logits, position * vocabSize, vocabSize);
    if (best === eId) {
      const index = pickCandidate(candVecs, types, present, hidden, position * dModel, lastField(text.join('')), dModel);
      text.push(candidates[index]?.id ?? '<bad>');
      out.push(best);
    } else {
      out.push(best);
      if (best === file.out.eos) break;
      text.push(file.out.itos[best] ?? '<unk>');
    }
  }
  return { text: text.join(''), eId, tokens: out };
}
