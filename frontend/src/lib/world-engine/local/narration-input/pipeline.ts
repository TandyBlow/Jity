/** One entry point for the model-facing input: normalize the four-field
 * projection, validate/fill the result block, serialize with the chosen
 * version, then check the tokenizer binding. Errors carry a stable stage and
 * code; there is no partial-text fallback. */
import { buildResult } from './build-result';
import { normalizeProjection } from './normalize';
import { renderLegacyInput } from './render-legacy';
import { serialize } from './serialize';
import { sha256Hex, utf8Hex } from './sha256';
import { validateTokenizerText, type TokenizerProfile } from './tokenizer';
import {
  NarrationInputError, type LengthLimits, type NarrationProjection, type RenderedNarrationInput,
  type ResultFill, type SerializedSegment,
} from './types';
import { LEGACY_SERIALIZER_VERSION, SERIALIZER_VERSION, narrationVersions } from './versions';
import { projectNarrationInput, type ProjectNarrationInputArgs } from './project';
import type { ProjectionResult } from './types';

export type NarrationModelPath = 'result-v2' | 'legacy';

export interface RenderNarrationInputOptions {
  model?: NarrationModelPath;
  /** Default true. Disable only when a different tokenizer is bound elsewhere. */
  checkTokenizer?: boolean;
  tokenizer?: TokenizerProfile;
  /** Optional hard limits. Exceeding them is an error, never a truncation. */
  limits?: Partial<LengthLimits>;
  /** Reference-harness option: serialize the stored result block without
   * running `buildResult` (used by the frozen negative vectors). */
  skipBuild?: boolean;
}

function runStage<T>(stage: 'normalize' | 'build' | 'serialize' | 'tokenizer', fn: () => T): T {
  try {
    return fn();
  } catch (error) {
    if (error instanceof NarrationInputError) throw error.withStage(stage);
    throw error;
  }
}

export function renderNarrationInput(
  rawProjection: unknown,
  options: RenderNarrationInputOptions = {},
): RenderedNarrationInput {
  const model = options.model ?? 'result-v2';
  // The legacy serializer never reads the result block. Accept the old
  // three-field projection (the shape of the frozen v1 data) by filling an
  // empty result, but never rewrite a result that was actually supplied.
  const raw = model === 'legacy'
    && rawProjection !== null && typeof rawProjection === 'object' && !Array.isArray(rawProjection)
    && !('本回合状态' in rawProjection)
    ? { ...(rawProjection as Record<string, unknown>), 本回合状态: {} }
    : rawProjection;
  const normalized = runStage('normalize', () => normalizeProjection(raw));
  let projection: NarrationProjection = normalized.projection;
  let text: string;
  let segments: SerializedSegment[] = [];
  let resultFills: ResultFill[] = [];
  let serializerVersion: string;

  if (model === 'legacy') {
    text = renderLegacyInput(projection);
    serializerVersion = LEGACY_SERIALIZER_VERSION;
  } else if (options.skipBuild) {
    // The reference `make_case(skip_build=True)` path: only the serializer runs,
    // so a serializer error is labelled `serialize` there.
    const serialized = runStage('serialize', () => serialize(projection));
    text = serialized.text;
    segments = serialized.segments;
    serializerVersion = SERIALIZER_VERSION;
  } else {
    // Reference staging: `build_result` and `serialize` share the `build`
    // stage label in the frozen vectors. `detailStage` keeps the real step.
    const labelOr = <T>(fn: () => T, precise: 'build' | 'serialize'): T => {
      try {
        return fn();
      } catch (error) {
        if (error instanceof NarrationInputError) {
          throw error.withStage(precise).withReferenceStage('build');
        }
        throw error;
      }
    };
    const built = labelOr(() => buildResult(
      projection.上回合状态, projection.本回合变化, projection.本回合状态,
    ), 'build');
    projection = { ...projection, 本回合状态: built.result };
    resultFills = built.fills;
    const serialized = labelOr(() => serialize(projection), 'serialize');
    text = serialized.text;
    segments = serialized.segments;
    serializerVersion = SERIALIZER_VERSION;
  }

  if (options.checkTokenizer ?? true) {
    runStage('tokenizer', () => validateTokenizerText(text, options.tokenizer));
  }

  const charCount = Array.from(text).length;
  const bytes = new TextEncoder().encode(text);
  const limits = options.limits;
  if (limits?.maxChars != null && charCount > limits.maxChars) {
    throw new NarrationInputError('input_too_long', `serialized input has ${charCount} code points; limit ${limits.maxChars}`, '', {
      charCount, utf8Bytes: bytes.byteLength, maxChars: limits.maxChars, maxUtf8Bytes: limits.maxUtf8Bytes ?? null,
    }).withStage('serialize');
  }
  if (limits?.maxUtf8Bytes != null && bytes.byteLength > limits.maxUtf8Bytes) {
    throw new NarrationInputError('input_too_long', `serialized input has ${bytes.byteLength} UTF-8 bytes; limit ${limits.maxUtf8Bytes}`, '', {
      charCount, utf8Bytes: bytes.byteLength, maxChars: limits.maxChars ?? null, maxUtf8Bytes: limits.maxUtf8Bytes,
    }).withStage('serialize');
  }

  return {
    text,
    serializerVersion,
    sha256: sha256Hex(text),
    bytesUtf8Hex: utf8Hex(text),
    utf8Bytes: bytes.byteLength,
    charCount,
    segments,
    projection,
    normalization: normalized.ledger,
    resultFills,
    version: narrationVersions(serializerVersion as typeof SERIALIZER_VERSION),
  };
}

export interface RuntimeNarrationInput extends ProjectionResult {
  rendered: RenderedNarrationInput;
}

/** Project from the committed states and render in one call. */
export function buildNarrationInput(
  args: ProjectNarrationInputArgs, options: RenderNarrationInputOptions = {},
): RuntimeNarrationInput {
  const projected = projectNarrationInput(args);
  const rendered = renderNarrationInput(projected.projection, options);
  // Return the normalized/built projection that was actually serialized, not
  // the pre-normalization copy (which may still contain `3 分钟`).
  return { ...projected, projection: rendered.projection, rendered };
}
