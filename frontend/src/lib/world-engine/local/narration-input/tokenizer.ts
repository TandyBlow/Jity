/** YuYan character-tokenizer binding.
 *
 * The vocabulary file is the exact one the v2 arm was trained with
 * (`tokenizers/yuyan-v1/dict.txt`, 13,668 entries, no space/tab/newline
 * entries). The derived character set is committed beside it; the hash is
 * checked against the file and against the registered constant.
 */
import charsetData from './yuyan-charset-v1.json';
import { NarrationInputError } from './types';
import { isPythonSpace } from './normalize';
import { TOKENIZER_NAME, TOKENIZER_SHA256, TOKENIZER_VOCAB_SIZE } from './versions';

interface CharsetFile {
  version: string;
  source: string;
  sourceSha256: string;
  vocabSize: number;
  singleCodePoints: number;
  chars: string;
}

const data = charsetData as CharsetFile;
export const YUYAN_CHARSET_VERSION = data.version;
export const YUYAN_CHARSET_SOURCE_SHA256 = data.sourceSha256;
export const YUYAN_700M_CHARSET: ReadonlySet<string> = new Set(Array.from(data.chars));

export function assertTokenizerIdentity(): void {
  if (data.sourceSha256 !== TOKENIZER_SHA256) {
    throw new Error(`tokenizer charset source ${data.sourceSha256} != registered ${TOKENIZER_SHA256}`);
  }
  if (data.vocabSize !== TOKENIZER_VOCAB_SIZE) {
    throw new Error(`tokenizer vocab size ${data.vocabSize} != registered ${TOKENIZER_VOCAB_SIZE}`);
  }
}

export interface TokenizerProfile {
  name: string;
  sha256: string;
  vocab: ReadonlySet<string>;
}

export const YUYAN_TOKENIZER: TokenizerProfile = (() => {
  assertTokenizerIdentity();
  return { name: TOKENIZER_NAME, sha256: TOKENIZER_SHA256, vocab: YUYAN_700M_CHARSET };
})();

/** Refuse whitespace first, then out-of-vocabulary characters. Indexes are
 * Unicode code points, matching the Python profile checker. */
export function validateTokenizerText(text: string, profile: TokenizerProfile = YUYAN_TOKENIZER): string {
  let index = 0;
  for (const char of text) {
    if (char === '\r' || char === '\n' || isPythonSpace(char)) {
      throw new NarrationInputError('tokenizer_whitespace', `character U+${char.codePointAt(0)!.toString(16).toUpperCase().padStart(4, '0')} at index ${index} is whitespace and has no YuYan vocabulary entry`, `index ${index}`);
    }
    if (!profile.vocab.has(char)) {
      throw new NarrationInputError('tokenizer_oov', `character ${JSON.stringify(char)} (U+${char.codePointAt(0)!.toString(16).toUpperCase().padStart(4, '0')}) at index ${index} is not in the YuYan vocabulary`, `index ${index}`);
    }
    index += 1;
  }
  return text;
}
