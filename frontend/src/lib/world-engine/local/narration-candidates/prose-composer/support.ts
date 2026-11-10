/** Small text utilities shared by the composer. No world semantics here. */

export function hash32(text: string): number {
  let value = 0x811c9dc5;
  for (let index = 0; index < text.length; index += 1) {
    value ^= text.charCodeAt(index);
    value = Math.imul(value, 0x01000193) >>> 0;
  }
  return value >>> 0;
}

/** Deterministic 32-bit PRNG. A point always composes the same draft unless
 * the caller changes the seed. */
export function createRandom(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function clampInt(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) return min;
  return Math.min(max, Math.max(min, Math.round(value)));
}

export function charCount(text: string): number {
  return [...text].length;
}

/** Split prose into sentences without breaking 「」 dialogue. */
export function splitSentences(text: string): string[] {
  const result: string[] = [];
  let current = '';
  let depth = 0;
  for (const char of text) {
    current += char;
    if (char === '「') depth += 1;
    else if (char === '」') depth = Math.max(0, depth - 1);
    else if ((char === '。' || char === '！' || char === '？' || char === '…') && depth === 0) {
      if (char === '…') {
        const next = text[text.indexOf(current) + current.length];
        if (next === '…') continue;
      }
      result.push(current.trim());
      current = '';
    }
  }
  if (current.trim()) result.push(current.trim());
  return result;
}

export function stripQuotes(text: string): string {
  return text
    .trim()
    .replace(/^[「『“"']+/, '')
    .replace(/[」』”"']+$/, '')
    .trim();
}

export function normalizeClause(text: string): string {
  return stripQuotes(text).replace(/[。；;]+$/u, '').trim();
}

/** Character bigrams, used for echo detection. */
export function bigrams(text: string): Set<string> {
  const stripped = text.replace(/[\s，。！？、；：「」『』“”…—]/gu, '');
  const result = new Set<string>();
  for (let index = 0; index + 1 < stripped.length; index += 1) {
    result.add(stripped.slice(index, index + 2));
  }
  return result;
}

export function overlapRatio(left: string, right: string): number {
  const a = bigrams(left);
  const b = bigrams(right);
  if (!a.size || !b.size) return 0;
  let shared = 0;
  for (const item of a) if (b.has(item)) shared += 1;
  return shared / Math.max(a.size, b.size);
}

export function paragraphStartsWith(paragraph: string, prefix: string): boolean {
  return paragraph.trim().startsWith(prefix.trim());
}

export function firstClause(text: string): string {
  const parts = text.split(/[，。；：]/u).map((part) => part.trim()).filter(Boolean);
  return parts[0] ?? text.trim();
}

export function lastSentence(text: string): string {
  const sentences = splitSentences(text);
  return sentences[sentences.length - 1] ?? '';
}

/** A faithful clause may contain slot placeholders. Supported:
 * {name} for the beat's actor, {actor:ID} for any cast member. */
export function fillSlots(
  template: string,
  names: ReadonlyMap<string, string>,
  actorId?: string,
): string {
  return template.replace(/\{(actor:([^}]+)|name)\}/gu, (match, token: string) => {
    if (token === 'name') return actorId ? names.get(actorId) ?? match : match;
    const id = token.slice('actor:'.length);
    return names.get(id) ?? match;
  });
}

export function ensurePeriod(text: string): string {
  const trimmed = text.trim();
  if (!trimmed) return '';
  return /[。！？…」』”]$/u.test(trimmed) ? trimmed : `${trimmed}。`;
}

export function uniquePush<T>(list: T[], value: T): void {
  if (!list.includes(value)) list.push(value);
}
