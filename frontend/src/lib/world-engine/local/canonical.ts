/** world-canonical-v1 byte encoder and SHA-256, ported from the Python kernel
 * so browser and Python digests can be compared byte-for-byte. Object keys are
 * ASCII and sorted by code point; numbers are safe integers; strings are
 * UTF-8. The digest is async because browsers expose SHA-256 only through
 * SubtleCrypto. */

export const MAX_SAFE = 2 ** 53 - 1;

function assertUnicode(value: unknown): void {
  if (typeof value === 'string') {
    for (let index = 0; index < value.length; index++) {
      const code = value.charCodeAt(index);
      if (code >= 0xd800 && code <= 0xdbff) {
        const low = value.charCodeAt(index + 1);
        if (!(low >= 0xdc00 && low <= 0xdfff)) throw new Error('unpaired Unicode surrogate');
        index++;
      } else if (code >= 0xdc00 && code <= 0xdfff) {
        throw new Error('unpaired Unicode surrogate');
      }
    }
    return;
  }
  if (Array.isArray(value)) { for (const item of value) assertUnicode(item); return; }
  if (value && typeof value === 'object') {
    for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
      assertUnicode(key);
      assertUnicode(item);
    }
  }
}

function pushAscii(out: number[], text: string): void {
  for (let index = 0; index < text.length; index++) out.push(text.charCodeAt(index));
}

function encode(value: unknown, out: number[]): void {
  if (value === null) { pushAscii(out, 'null'); return; }
  if (typeof value === 'boolean') { pushAscii(out, value ? 'true' : 'false'); return; }
  if (typeof value === 'string') {
    out.push(0x22);
    const encoded = new TextEncoder().encode(value);
    for (let index = 0; index < encoded.length; index++) {
      const byte = encoded[index];
      if (byte === 0x22) { out.push(0x5c, 0x22); continue; }
      if (byte === 0x5c) { out.push(0x5c, 0x5c); continue; }
      if (byte < 0x20) { pushAscii(out, `\\u${byte.toString(16).padStart(4, '0')}`); continue; }
      out.push(byte);
    }
    out.push(0x22);
    return;
  }
  if (typeof value === 'number') {
    if (!Number.isFinite(value) || !Number.isSafeInteger(value)) throw new Error('expected a safe integer');
    pushAscii(out, String(value));
    return;
  }
  if (Array.isArray(value)) {
    out.push(0x5b);
    value.forEach((item, index) => { if (index) out.push(0x2c); encode(item, out); });
    out.push(0x5d);
    return;
  }
  if (typeof value === 'object') {
    const record = value as Record<string, unknown>;
    const keys = Object.keys(record);
    for (const key of keys) if (!/^[\x00-\x7f]*$/.test(key)) throw new Error('object keys must be ASCII strings');
    keys.sort();
    out.push(0x7b);
    keys.forEach((key, index) => {
      if (index) out.push(0x2c);
      encode(key, out);
      out.push(0x3a);
      encode(record[key], out);
    });
    out.push(0x7d);
    return;
  }
  throw new Error(`not a JSON value: ${typeof value}`);
}

export function canonicalBytes(value: unknown): Uint8Array {
  assertUnicode(value);
  const out: number[] = [];
  encode(value, out);
  return new Uint8Array(out);
}

export async function canonicalDigest(value: unknown): Promise<string> {
  const bytes = canonicalBytes(value);
  if (!globalThis.crypto?.subtle) throw new Error('SubtleCrypto unavailable');
  const digest = await globalThis.crypto.subtle.digest('SHA-256', bytes.buffer as ArrayBuffer);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, '0')).join('');
}

export function canonicalJson(value: unknown): string {
  return new TextDecoder().decode(canonicalBytes(value));
}
