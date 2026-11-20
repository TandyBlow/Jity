/** Static-world entry point: strict JSON reading, full `WorldState` validation,
 * S0 reconstruction and registered-digest verification.
 *
 * The browser must not start a game from a file that merely parses. This
 * loader re-implements the checks the Python contract applies to
 * `WorldInitialState` / `WorldState`, rejects duplicate JSON keys and
 * non-contract numbers before `JSON.parse` can hide them, rebuilds S0 from
 * `initial`, and compares the canonical SHA-256 with the digest registered for
 * the asset. A mismatch is a refusal, never a warning.
 *
 * `fileSha256Lf` is the SHA-256 of the UTF-8 text after CRLF/CR is normalized
 * to LF. That matches the committed git blob independently of a Windows
 * working-tree checkout. */
import { canonicalDigest, canonicalJson } from './canonical';
import {
  buildInitialState, KernelViolation, normalizeInitialState, normalizeWorldState, stateDigest,
  validateWorldPositions,
} from './state';
import type { Id, InitialState, InitialTemplate, WorldState } from '../types';

export type StaticWorldErrorReason = 'json' | 'file_hash' | 'schema' | 'digest' | 'initial_digest' | 's0';

export class StaticWorldError extends Error {
  readonly name = 'StaticWorldError';
  constructor(readonly reason: StaticWorldErrorReason, detail: string) {
    super(`${reason}: ${detail}`);
  }
}

export interface StaticWorldRegistration {
  /** world-canonical-v1 SHA-256 of the full static `WorldState` snapshot. */
  stateDigest: string;
  /** Optional SHA-256 of the LF-normalized UTF-8 file text. */
  fileSha256Lf?: string;
  /** Optional world-canonical-v1 SHA-256 of `initial` alone. */
  initialDigest?: string;
}

export interface LoadedStaticWorld {
  worldId: Id;
  /** Full initial projection, including `worldId`. */
  initial: InitialState;
  /** The same opening projection in the shape `LocalGameSession.create` takes. */
  template: InitialTemplate;
  /** The file's current snapshot, normalized to contract shape. */
  state: WorldState;
  /** The state rebuilt from `initial`; equal to `state` when `requireS0`. */
  s0: WorldState;
  stateDigest: string;
  s0Digest: string;
  initialDigest: string;
  fileSha256Lf: string;
  counts: { locations: number; items: number; characters: number; tasks: number };
}

const HEX64 = /^[0-9a-f]{64}$/;

/** Normalize line endings exactly like Python text mode before hashing. */
export function normalizeWorldText(text: string): string {
  return text.replace(/\r\n?/g, '\n');
}

async function sha256Text(text: string): Promise<string> {
  const bytes = new TextEncoder().encode(text);
  if (!globalThis.crypto?.subtle) throw new StaticWorldError('file_hash', 'SubtleCrypto unavailable');
  const digest = await globalThis.crypto.subtle.digest('SHA-256', bytes.buffer as ArrayBuffer);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, '0')).join('');
}

function parseError(detail: string): never {
  throw new StaticWorldError('json', detail);
}

/** Strict JSON parser for the static asset. Unlike `JSON.parse` it refuses
 * duplicate object keys, non-integer/unsafe numbers (including 1.5, 1e999 and
 * 9007199254740993), non-ASCII object keys and unpaired surrogate escapes. */
export function parseStaticWorldJson(text: string): unknown {
  let index = 0;
  const fail = (detail: string): never => parseError(`${detail} at offset ${index}`);
  const space = (): void => {
    while (index < text.length) {
      const ch = text[index];
      if (ch !== ' ' && ch !== '\t' && ch !== '\n' && ch !== '\r') return;
      index += 1;
    }
  };
  const hex4 = (): number => {
    const raw = text.slice(index, index + 4);
    if (!/^[0-9a-fA-F]{4}$/.test(raw)) fail('invalid \\u escape');
    index += 4;
    return Number.parseInt(raw, 16);
  };
  const string = (): string => {
    if (text[index] !== '"') fail('expected a string');
    index += 1;
    let out = '';
    while (index < text.length) {
      const ch = text[index];
      index += 1;
      if (ch === '"') return out;
      if (ch !== '\\') {
        if (ch.charCodeAt(0) < 0x20) fail('unescaped control character in string');
        out += ch;
        continue;
      }
      const escape = text[index];
      index += 1;
      switch (escape) {
        case '"': out += '"'; break;
        case '\\': out += '\\'; break;
        case '/': out += '/'; break;
        case 'b': out += '\b'; break;
        case 'f': out += '\f'; break;
        case 'n': out += '\n'; break;
        case 'r': out += '\r'; break;
        case 't': out += '\t'; break;
        case 'u': {
          const code = hex4();
          if (code >= 0xd800 && code <= 0xdbff) {
            if (text[index] !== '\\' || text[index + 1] !== 'u') fail('unpaired high surrogate');
            index += 2;
            const low = hex4();
            if (low < 0xdc00 || low > 0xdfff) fail('unpaired high surrogate');
            out += String.fromCharCode(code, low);
          } else if (code >= 0xdc00 && code <= 0xdfff) {
            fail('unpaired low surrogate');
          } else {
            out += String.fromCharCode(code);
          }
          break;
        }
        default: fail('invalid escape sequence');
      }
    }
    return fail('unterminated string');
  };
  const number = (): number => {
    const start = index;
    let negative = false;
    if (text[index] === '-') { negative = true; index += 1; }
    const intStart = index;
    if (text[index] === '0') {
      index += 1;
    } else if (text[index] >= '1' && text[index] <= '9') {
      while (text[index] >= '0' && text[index] <= '9') index += 1;
    } else {
      fail('invalid number');
    }
    const integerDigits = text.slice(intStart, index);
    let fractionDigits = '';
    if (text[index] === '.') {
      index += 1;
      const fractionStart = index;
      while (text[index] >= '0' && text[index] <= '9') index += 1;
      fractionDigits = text.slice(fractionStart, index);
      if (!fractionDigits.length) fail('number needs digits after the decimal point');
    }
    let exponent = 0;
    if (text[index] === 'e' || text[index] === 'E') {
      index += 1;
      let exponentNegative = false;
      if (text[index] === '+' || text[index] === '-') {
        exponentNegative = text[index] === '-';
        index += 1;
      }
      const exponentStart = index;
      while (text[index] >= '0' && text[index] <= '9') index += 1;
      if (index === exponentStart) fail('number needs exponent digits');
      const rawExponent = text.slice(exponentStart, index);
      if (rawExponent.length > 6) fail('number exponent is out of range');
      exponent = Number.parseInt(rawExponent, 10) * (exponentNegative ? -1 : 1);
    }
    const token = text.slice(start, index);
    let digits = (integerDigits + fractionDigits).replace(/^0+/, '');
    const scale = exponent - fractionDigits.length;
    if (!digits.length) return 0;
    if (scale >= 0) {
      if (digits.length + scale > 17) fail('number is outside the safe-integer range');
      digits += '0'.repeat(scale);
    } else {
      const drop = -scale;
      if (drop > digits.length) {
        if (!/^0*$/.test(digits)) fail('number is not an integer');
        return 0;
      }
      const dropped = digits.slice(digits.length - drop);
      if (!/^0*$/.test(dropped)) fail('number is not an integer');
      digits = digits.slice(0, digits.length - drop);
      if (!digits.length) return 0;
    }
    if (digits.length > 16) fail('number is outside the safe-integer range');
    const value = BigInt(digits) * (negative ? -1n : 1n);
    if (value < -9007199254740991n || value > 9007199254740991n) {
      fail(`number ${token} is outside the safe-integer range`);
    }
    return Number(value);
  };
  const value = (): unknown => {
    space();
    const ch = text[index];
    if (ch === '{') {
      index += 1;
      space();
      const out: Record<string, unknown> = {};
      if (text[index] === '}') { index += 1; return out; }
      while (true) {
        space();
        const key = string();
        if (!/^[\x00-\x7f]*$/.test(key)) fail('object keys must be ASCII strings');
        if (Object.prototype.hasOwnProperty.call(out, key)) fail(`duplicate JSON key ${key}`);
        space();
        if (text[index] !== ':') fail('expected : after object key');
        index += 1;
        Object.defineProperty(out, key, { value: value(), enumerable: true, writable: true, configurable: true });
        space();
        if (text[index] === ',') { index += 1; continue; }
        if (text[index] === '}') { index += 1; return out; }
        fail('expected , or } in object');
      }
    }
    if (ch === '[') {
      index += 1;
      space();
      const out: unknown[] = [];
      if (text[index] === ']') { index += 1; return out; }
      while (true) {
        out.push(value());
        space();
        if (text[index] === ',') { index += 1; continue; }
        if (text[index] === ']') { index += 1; return out; }
        fail('expected , or ] in array');
      }
    }
    if (ch === '"') return string();
    if (text.startsWith('true', index)) { index += 4; return true; }
    if (text.startsWith('false', index)) { index += 5; return false; }
    if (text.startsWith('null', index)) { index += 4; return null; }
    if (ch === '-' || (ch >= '0' && ch <= '9')) return number();
    return fail('unexpected token');
  };
  const parsed = value();
  space();
  if (index !== text.length) fail('trailing characters after the JSON value');
  return parsed;
}

function omitWorldId(initial: InitialState): InitialTemplate {
  const template: Record<string, unknown> = { ...initial };
  delete template.worldId;
  return template as unknown as InitialTemplate;
}

function schemaError(error: unknown): never {
  if (error instanceof StaticWorldError) throw error;
  if (error instanceof KernelViolation) throw new StaticWorldError('schema', error.message);
  throw new StaticWorldError('schema', (error as Error).message);
}

/** Validate an already parsed value. This performs no digest comparison; it is
 * the synchronous half used by tests and by callers that keep a JSON object. */
export function readStaticWorldValue(value: unknown): {
  initial: InitialState; template: InitialTemplate; state: WorldState; s0: WorldState;
} {
  try {
    const initial = normalizeInitialState((value as { initial?: unknown } | null)?.initial);
    const state = normalizeWorldState(value, initial);
    const positionErrors = validateWorldPositions(state);
    if (positionErrors.length) throw new StaticWorldError('schema', positionErrors.join('; '));
    return { initial, template: omitWorldId(initial), state, s0: buildInitialState(initial) };
  } catch (error) {
    return schemaError(error);
  }
}

/** Read, validate and digest-check one static world file.
 *
 * The default `requireS0` enforces the asset contract: the file's current
 * snapshot is the opening state rebuilt from `initial`. Pass
 * `{ requireS0: false }` only for inspection of a non-opening static snapshot;
 * game start must keep the default. */
export async function loadStaticWorld(
  text: string,
  registration: StaticWorldRegistration,
  options: { requireS0?: boolean } = {},
): Promise<LoadedStaticWorld> {
  if (!HEX64.test(registration.stateDigest)) {
    throw new StaticWorldError('digest', 'registered stateDigest is not a lowercase SHA-256');
  }
  if (registration.fileSha256Lf != null && !HEX64.test(registration.fileSha256Lf)) {
    throw new StaticWorldError('file_hash', 'registered fileSha256Lf is not a lowercase SHA-256');
  }
  if (registration.initialDigest != null && !HEX64.test(registration.initialDigest)) {
    throw new StaticWorldError('initial_digest', 'registered initialDigest is not a lowercase SHA-256');
  }
  const normalizedText = normalizeWorldText(text);
  const fileSha256Lf = await sha256Text(normalizedText);
  if (registration.fileSha256Lf != null && fileSha256Lf !== registration.fileSha256Lf) {
    throw new StaticWorldError('file_hash', `file hash ${fileSha256Lf} differs from the registered value`);
  }
  let parsed: unknown;
  try {
    parsed = parseStaticWorldJson(text);
  } catch (error) {
    throw error instanceof StaticWorldError ? error : new StaticWorldError('json', (error as Error).message);
  }
  const read = readStaticWorldValue(parsed);
  const initialDigest = await canonicalDigest(read.initial);
  if (registration.initialDigest != null && initialDigest !== registration.initialDigest) {
    throw new StaticWorldError('initial_digest', `initial digest ${initialDigest} differs from the registered value`);
  }
  const currentDigest = await stateDigest(read.state);
  if (currentDigest !== registration.stateDigest) {
    throw new StaticWorldError('digest', `state digest ${currentDigest} differs from the registered value`);
  }
  const s0Digest = await stateDigest(read.s0);
  if (options.requireS0 !== false && canonicalJson(read.state) !== canonicalJson(read.s0)) {
    throw new StaticWorldError('s0', 'static current snapshot differs from S0 rebuilt from initial');
  }
  return {
    worldId: read.initial.worldId,
    initial: read.initial,
    template: read.template,
    state: read.state,
    s0: read.s0,
    stateDigest: currentDigest,
    s0Digest,
    initialDigest,
    fileSha256Lf,
    counts: {
      locations: Object.keys(read.state.locations).length,
      items: Object.keys(read.state.items).length,
      characters: Object.keys(read.state.characters).length,
      tasks: Object.values(read.state.characters).reduce((sum, character) => sum + Object.keys(character.tasks).length, 0),
    },
  };
}
