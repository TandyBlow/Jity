/** SHA-256 over the UTF-8 bytes of a serialized input. Browsers expose this
 * only asynchronously; the serializers return the promise so callers can log
 * the hash without blocking the text handoff. */
export async function sha256Utf8(text: string): Promise<string> {
  const subtle = globalThis.crypto?.subtle;
  if (!subtle) throw new Error('SHA-256 is unavailable: globalThis.crypto.subtle is missing');
  const digest = await subtle.digest('SHA-256', new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, '0')).join('');
}
