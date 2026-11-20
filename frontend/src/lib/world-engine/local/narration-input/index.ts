/** Public entry for the narration input adapter. The main integration only
 * needs these exports: project once, then serialize with the version that
 * matches the model. */
export { projectNarrationInput } from './project';
export type { ProjectNarrationInputArgs } from './project';
export { renderLegacyInput, assertNarrationProjection } from './render-legacy';
export { renderResultInput, renderResultBlock } from './render-result';
export type { RenderOptions } from './render-common';
export { assertEncodable, YUYAN_700M_CHARSET, YUYAN_CHARSET_VERSION, YUYAN_CHARSET_SOURCE_SHA256 } from './charset';
export { compareCodePoints } from './code-points';
export { sha256Utf8 } from './sha256';
export * from './types';
