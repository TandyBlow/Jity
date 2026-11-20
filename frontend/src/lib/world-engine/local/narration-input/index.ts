/** Public entry for the narration input adapter.
 *
 *   const projected = projectNarrationInput({ before, after, delta, timeAdvance, viewpointId });
 *   const { text } = renderNarrationInput(projected.projection);
 *
 * `renderNarrationInput` defaults to the trained `yuyan-prose-result-v2`
 * format. Pass `{ model: 'legacy' }` only for the existing legacy checkpoint.
 */
export { projectNarrationInput } from './project';
export type { ProjectNarrationInputArgs } from './project';
export { normalizeProjection } from './normalize';
export { buildResult } from './build-result';
export { serialize, serializeText } from './serialize';
export { renderLegacyInput } from './render-legacy';
export { renderNarrationInput, buildNarrationInput } from './pipeline';
export type { NarrationModelPath, RenderNarrationInputOptions, RuntimeNarrationInput } from './pipeline';
export { validateTokenizerText, YUYAN_700M_CHARSET, YUYAN_TOKENIZER, YUYAN_CHARSET_SOURCE_SHA256 } from './tokenizer';
export { compareCodePoints } from './code-points';
export { sha256Hex, utf8Hex } from './sha256';
export {
  PROJECTION_VERSION, SERIALIZER_VERSION, LEGACY_PROJECTION_VERSION,
  LEGACY_SERIALIZER_VERSION, MODEL_TEMPLATE_VERSION, TOKENIZER_NAME, TOKENIZER_SHA256,
  TOKENIZER_VOCAB_SIZE, narrationVersions,
} from './versions';
export type { NarrationVersionSet } from './versions';
export * from './types';
