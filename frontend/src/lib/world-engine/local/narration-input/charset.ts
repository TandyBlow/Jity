/** Character-level safety check for the legacy YuYan path.
 *
 * The model's vocabulary has no space, tab, CR or LF token. A prompt with any
 * of them makes the tokenizer throw `invalid unordered_map<K, T> key`, which
 * aborts generation rather than just changing a glyph. This module rejects
 * such text before it reaches the model and also rejects code points outside
 * the recorded vocabulary.
 *
 * The charset file is derived from the YuYan-700M vocabulary; the derivation
 * and source hash are in the file's metadata and in the lane handoff.
 */
import charsetData from './yuyan-charset-v1.json';
import { NarrationInputError } from './types';

interface CharsetFile {
  version: string;
  source: string;
  sourceSha256: string;
  symbols: number;
  chars: string;
}

const data = charsetData as CharsetFile;
export const YUYAN_CHARSET_VERSION = data.version;
export const YUYAN_CHARSET_SOURCE_SHA256 = data.sourceSha256;
export const YUYAN_700M_CHARSET: ReadonlySet<string> = new Set(Array.from(data.chars));

export interface EncodabilityOptions {
  /** null disables the vocabulary check (a different tokenizer or a test
   * fixture). The whitespace check stays on by default because both serialized
   * formats are intentionally separator-free. */
  charset?: ReadonlySet<string> | null;
  rejectWhitespace?: boolean;
}

/** Reject whitespace and out-of-vocabulary code points with stable error
 * categories. No normalization or silent replacement: a caller that needs a
 * different tokenizer must pass its own charset. */
export function assertEncodable(text: string, options: EncodabilityOptions = {}): void {
  const rejectWhitespace = options.rejectWhitespace ?? true;
  const charset = options.charset === undefined ? YUYAN_700M_CHARSET : options.charset;
  const chars = Array.from(text);
  let offset = 0;
  for (const char of chars) {
    if (rejectWhitespace && /\s/u.test(char)) {
      throw new NarrationInputError('whitespace', `serialized input contains whitespace at code unit ${offset}`, {
        char,
        codePoint: `U+${(char.codePointAt(0) as number).toString(16).toUpperCase().padStart(4, '0')}`,
        offset,
      });
    }
    if (charset && !charset.has(char)) {
      throw new NarrationInputError('oov', `serialized input contains an out-of-vocabulary character at code unit ${offset}`, {
        char,
        codePoint: `U+${(char.codePointAt(0) as number).toString(16).toUpperCase().padStart(4, '0')}`,
        offset,
      });
    }
    offset += char.length;
  }
}

/** Python `len` and the training rows count Unicode code points, not UTF-16
 * code units. Keep both numbers so a limit can be audited. */
export function codePointLength(text: string): number {
  return Array.from(text).length;
}
