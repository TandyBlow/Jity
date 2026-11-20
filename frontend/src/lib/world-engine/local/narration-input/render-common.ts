/** Shared finalization for both serializers: encodability, measured length,
 * optional hard limits and the UTF-8 hash. Neither serializer truncates. */
import type {
  NarrationProjection, RenderedNarrationInput,
} from './types';
import { NarrationInputError } from './types';
import { assertEncodable, codePointLength, type EncodabilityOptions } from './charset';
import { sha256Utf8 } from './sha256';

export interface RenderOptions extends EncodabilityOptions {
  /** Enforce the projection's length policy. Default true. */
  enforceLength?: boolean;
}

function enforceLength(text: string, projection: NarrationProjection, bytes: number, chars: number): void {
  const policy = projection.policy?.length;
  if (!policy) return;
  if (policy.maxChars !== null && chars > policy.maxChars) {
    throw new NarrationInputError('too_long', `serialized input has ${chars} code points; limit ${policy.maxChars}`, {
      charCount: chars, utf16CodeUnits: text.length, utf8Bytes: bytes,
      maxChars: policy.maxChars, maxUtf8Bytes: policy.maxUtf8Bytes,
    });
  }
  if (policy.maxUtf8Bytes !== null && bytes > policy.maxUtf8Bytes) {
    throw new NarrationInputError('too_long', `serialized input has ${bytes} UTF-8 bytes; limit ${policy.maxUtf8Bytes}`, {
      charCount: chars, utf16CodeUnits: text.length, utf8Bytes: bytes,
      maxChars: policy.maxChars, maxUtf8Bytes: policy.maxUtf8Bytes,
    });
  }
}

export function finalizeRenderedInput(
  text: string,
  projection: NarrationProjection,
  serializerVersion: RenderedNarrationInput['serializerVersion'],
  options: RenderOptions,
): RenderedNarrationInput {
  assertEncodable(text, options);
  const bytes = new TextEncoder().encode(text).byteLength;
  const chars = codePointLength(text);
  if (options.enforceLength ?? true) enforceLength(text, projection, bytes, chars);
  return {
    text,
    utf8Bytes: bytes,
    utf8Sha256: sha256Utf8(text),
    charCount: chars,
    utf16CodeUnits: text.length,
    serializerVersion,
  };
}
