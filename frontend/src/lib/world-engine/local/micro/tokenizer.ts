/** Browser BERT tokenizer matching transformers' slow BertTokenizer.
 * Vocab order is the file order; [CLS]/[SEP]/[UNK] come from the vocab. */
const CLS = '[CLS]';
const SEP = '[SEP]';
const UNK = '[UNK]';

const CJK: Array<[number, number]> = [
  [0x4e00, 0x9fff], [0x3400, 0x4dbf], [0x20000, 0x2a6df], [0x2a700, 0x2b73f],
  [0x2b740, 0x2b81f], [0x2b820, 0x2ceaf], [0xf900, 0xfaff], [0x2f800, 0x2fa1f],
];

function isCjk(code: number): boolean {
  return CJK.some(([low, high]) => code >= low && code <= high);
}

function isPunctuation(ch: string): boolean {
  return /\p{P}/u.test(ch);
}

function stripAccents(text: string): string {
  return text.normalize('NFD').replace(/\p{Mn}/gu, '');
}

function basicTokens(text: string): string[] {
  const cleaned = text.replace(/[\u0000�]/gu, '').replace(/\s+/gu, ' ').trim();
  let spaced = '';
  for (const ch of cleaned) {
    spaced += isCjk(ch.codePointAt(0) ?? 0) ? ` ${ch} ` : ch;
  }
  const out: string[] = [];
  for (const word of spaced.split(/\s+/u)) {
    if (!word) continue;
    const lowered = stripAccents(word.toLowerCase());
    let current = '';
    for (const ch of lowered) {
      if (isPunctuation(ch)) {
        if (current) out.push(current);
        out.push(ch);
        current = '';
      } else {
        current += ch;
      }
    }
    if (current) out.push(current);
  }
  return out;
}

export interface BertTokenizer {
  encode(text: string, maxLength?: number): number[];
  encodePair(a: string, b: string, maxLength?: number): { ids: number[]; mask: number[] };
  vocabSize: number;
}

export function createBertTokenizer(vocabText: string): BertTokenizer {
  const vocab = new Map<string, number>();
  vocabText.split(/\r?\n/u).forEach((token, index) => {
    if (token) vocab.set(token, index);
  });
  const unkId = vocab.get(UNK) ?? 100;
  const idOf = (token: string): number => vocab.get(token) ?? unkId;

  function wordpiece(token: string): string[] {
    if (token.length > 100) return [UNK];
    const pieces: string[] = [];
    let start = 0;
    while (start < token.length) {
      let end = token.length;
      let piece: string | null = null;
      while (start < end) {
        const candidate = (start > 0 ? '##' : '') + token.slice(start, end);
        if (vocab.has(candidate)) {
          piece = candidate;
          break;
        }
        end -= 1;
      }
      if (piece === null) return [UNK];
      pieces.push(piece);
      start = end;
    }
    return pieces;
  }

  const SPECIAL = /\[(?:PAD|UNK|CLS|SEP|MASK)\]/gu;

  function tokens(text: string): string[] {
    // transformers keeps literal special tokens as single units.
    const out: string[] = [];
    let last = 0;
    SPECIAL.lastIndex = 0;
    for (let match = SPECIAL.exec(text); match; match = SPECIAL.exec(text)) {
      if (match.index > last) out.push(...basicTokens(text.slice(last, match.index)).flatMap(wordpiece));
      out.push(match[0]);
      last = match.index + match[0].length;
    }
    if (last < text.length) out.push(...basicTokens(text.slice(last)).flatMap(wordpiece));
    return out;
  }

  return {
    vocabSize: vocab.size,
    encode(text, maxLength = 128) {
      const body = tokens(text).slice(0, Math.max(0, maxLength - 2)).map(idOf);
      return [idOf(CLS), ...body, idOf(SEP)];
    },
    encodePair(a, b, maxLength = 128) {
      const left = tokens(a);
      const right = tokens(b);
      const budget = Math.max(0, maxLength - 3);
      while (left.length + right.length > budget) {
        // transformers' longest_first: ties truncate the second sequence.
        if (left.length > right.length) left.pop();
        else right.pop();
        if (!left.length && !right.length) break;
      }
      const ids = [idOf(CLS), ...left.map(idOf), idOf(SEP), ...right.map(idOf), idOf(SEP)];
      return { ids, mask: ids.map(() => 1) };
    },
  };
}
