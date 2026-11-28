/** N10 句界模型的浏览器实现：murmurhash3_32 哈希 + 线性权重，无运行时依赖。
 *  权重见 boundary-model.json；特征与训练脚本 features() 逐项一致。 */
import asset from './boundary-model.json';

export interface BoundaryPair {
  textA: string;
  kindA: string;
  textB: string;
  kindB: string;
  prev?: string;
  next?: string;
}

const HASH_DIM = 4096;
const WEIGHTS = asset.weights as number[];

function murmurhash3_32(key: string, seed = 0): number {
  const bytes = new TextEncoder().encode(key);
  const c1 = 0xcc9e2d51;
  const c2 = 0x1b873593;
  let h1 = seed >>> 0;
  const len = bytes.length;
  const blocks = len >> 2;
  for (let i = 0; i < blocks; i += 1) {
    let k1 = (bytes[i * 4] | (bytes[i * 4 + 1] << 8) | (bytes[i * 4 + 2] << 16) | (bytes[i * 4 + 3] << 24)) >>> 0;
    k1 = Math.imul(k1, c1) >>> 0;
    k1 = ((k1 << 15) | (k1 >>> 17)) >>> 0;
    k1 = Math.imul(k1, c2) >>> 0;
    h1 = (h1 ^ k1) >>> 0;
    h1 = ((h1 << 13) | (h1 >>> 19)) >>> 0;
    h1 = (Math.imul(h1, 5) + 0xe6546b64) >>> 0;
  }
  let k1 = 0;
  const tail = blocks * 4;
  switch (len & 3) {
    case 3: k1 ^= bytes[tail + 2] << 16; // falls through
    case 2: k1 ^= bytes[tail + 1] << 8; // falls through
    case 1:
      k1 ^= bytes[tail];
      k1 = Math.imul(k1, c1) >>> 0;
      k1 = ((k1 << 15) | (k1 >>> 17)) >>> 0;
      k1 = Math.imul(k1, c2) >>> 0;
      h1 = (h1 ^ k1) >>> 0;
      break;
    default: break;
  }
  h1 = (h1 ^ len) >>> 0;
  h1 ^= h1 >>> 16;
  h1 = Math.imul(h1, 0x85ebca6b) >>> 0;
  h1 ^= h1 >>> 13;
  h1 = Math.imul(h1, 0xc2b2ae35) >>> 0;
  h1 ^= h1 >>> 16;
  return h1 | 0;
}

function grams(text: string, limit: number): string[] {
  const out: string[] = [];
  for (let i = 0; i + 1 < text.length && out.length < limit; i += 1) out.push(text.slice(i, i + 2));
  return out;
}

export function boundaryFeatures(pair: BoundaryPair, names: string[]): string[] {
  const a = pair.textA;
  const b = pair.textB;
  const prev = pair.prev ?? '';
  const next = pair.next ?? '';
  const out = [
    `k:${pair.kindA}>${pair.kindB}`,
    `la:${Math.min(Math.floor(a.length / 8), 6)}`,
    `lb:${Math.min(Math.floor(b.length / 8), 6)}`,
    ...grams(a, 40).map((g) => `ga:${g}`),
    ...grams(b, 40).map((g) => `gb:${g}`),
  ];
  if (names.some((name) => b.startsWith(name))) out.push('bname');
  if (names.some((name) => a.startsWith(name))) out.push('aname');
  if (['屋', '右', '左', '巷'].includes(b.slice(0, 1))) out.push('bplace');
  out.push(...grams(prev, 20).map((g) => `gp:${g}`));
  out.push(...grams(next, 20).map((g) => `gn:${g}`));
  if (!prev) out.push('bos');
  if (!next) out.push('eos');
  return out;
}

export function boundaryScore(pair: BoundaryPair, names: string[]): number {
  let total = asset.intercept;
  for (const feature of boundaryFeatures(pair, names)) {
    total += WEIGHTS[Math.abs(murmurhash3_32(feature)) % HASH_DIM];
  }
  return total;
}

/** true = 另起一句；false = 并进上一句。 */
export function boundaryDecision(pair: BoundaryPair, names: string[]): boolean {
  return boundaryScore(pair, names) > 0;
}
