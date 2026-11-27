/** Browser-side encoder for the v3 candidate-pointer model.
 *
 * Reads `/micro/v3-encoding.json` (exported by `export_v3_encoding.py`) and
 * turns a point into exactly the tensors the Python exporter produced:
 * MiniRBT source ids padded to 96, the prefix as output-vocab seed ids, and
 * candidate entity names as char-level ids with their type ids. */
import type { BertTokenizer } from './tokenizer';

export interface V3EncodingFile {
  constants: { maxSource: number; maxTarget: number; maxTokens: number; maxCandidates: number; candChars: number; heads: number; headDim: number; dModel: number };
  patterns: { out: string; src: string; cand: string };
  out: { itos: string[]; stoi: Record<string, number>; pad: number; bos: number; eos: number; unk: number };
  cand: { itos: string[]; stoi: Record<string, number>; pad: number; unk: number };
  typeId: Record<string, number>;
}

export interface V3CandidateInput { id: string; name: string; type: string }

export interface V3Tensors {
  srcIds: number[];
  srcMask: number[];
  seedIds: number[];
  candIds: number[];
  candMask: number[];
  candTypes: number[];
}

export function parseEncoding(json: V3EncodingFile): V3EncodingFile {
  return json;
}

function outTokens(file: V3EncodingFile, text: string): string[] {
  const pattern = new RegExp(file.patterns.out, 'gu');
  return text.match(pattern) ?? [];
}

export function encodeSource(tokenizer: BertTokenizer, input: string, maxSource: number): { ids: number[]; mask: number[] } {
  const ids = tokenizer.encode(input, maxSource);
  const mask = ids.map(() => 1);
  while (ids.length < maxSource) { ids.push(0); mask.push(0); }
  return { ids, mask };
}

export function seedIds(file: V3EncodingFile, prefix: string): number[] {
  const body = outTokens(file, prefix).slice(0, file.constants.maxTarget - 2);
  return body.map((token) => file.out.stoi[token] ?? file.out.unk);
}

export function encodeCandidates(file: V3EncodingFile, candidates: V3CandidateInput[]): Pick<V3Tensors, 'candIds' | 'candMask' | 'candTypes'> {
  const { maxCandidates, candChars } = file.constants;
  const candIds = new Array<number>(maxCandidates * candChars).fill(file.cand.pad);
  const candMask = new Array<number>(maxCandidates * candChars).fill(0);
  const candTypes = new Array<number>(maxCandidates).fill(0);
  const pattern = new RegExp(file.patterns.cand, 'gu');
  candidates.slice(0, maxCandidates).forEach((candidate, index) => {
    // 与导出脚本一致：候选 token 覆盖「名字=id」。
    const tokens = ((candidate.name + '=' + candidate.id).match(pattern) ?? []).slice(0, candChars);
    tokens.forEach((token, offset) => {
      candIds[index * candChars + offset] = file.cand.stoi[token] ?? file.cand.unk;
      candMask[index * candChars + offset] = 1;
    });
    candTypes[index] = file.typeId[candidate.type] ?? 0;
  });
  return { candIds, candMask, candTypes };
}

export function encodePoint(file: V3EncodingFile, tokenizer: BertTokenizer, input: string, prefix: string, candidates: V3CandidateInput[]): V3Tensors {
  const source = encodeSource(tokenizer, input, file.constants.maxSource);
  return {
    srcIds: source.ids,
    srcMask: source.mask,
    seedIds: seedIds(file, prefix),
    ...encodeCandidates(file, candidates),
  };
}
