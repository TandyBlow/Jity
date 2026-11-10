/** Format and tokenizer identity, aligned with the v2 arm actually trained by
 * lane 10 (job 251206). Both sides must print these strings; do not reuse one
 * version name for a different byte format. */
export const PROJECTION_VERSION = 'narration-result-view-v2' as const;
export const SERIALIZER_VERSION = 'yuyan-prose-result-v2' as const;
export const LEGACY_PROJECTION_VERSION = 'narration-result-view-v1' as const;
export const LEGACY_SERIALIZER_VERSION = 'yuyan-prose-legacy-v1' as const;
export const MODEL_TEMPLATE_VERSION = 'yuyan-raw-completion-v1' as const;

export const TOKENIZER_NAME = 'yuyan-char-v1' as const;
export const TOKENIZER_PATH = 'tokenizer/yuyan-v1/dict.txt' as const;
export const TOKENIZER_SHA256 = '20287a9d1a2ec9d82b2a13f02c10c7b81e8bb015f114134bca6b06e5c8d376b4' as const;
export const TOKENIZER_VOCAB_SIZE = 13668 as const;

export interface NarrationVersionSet {
  projectionVersion: typeof PROJECTION_VERSION;
  serializerVersion: typeof SERIALIZER_VERSION | typeof LEGACY_SERIALIZER_VERSION;
  legacyProjectionVersion: typeof LEGACY_PROJECTION_VERSION;
  legacySerializerVersion: typeof LEGACY_SERIALIZER_VERSION;
  modelTemplateVersion: typeof MODEL_TEMPLATE_VERSION;
  tokenizerName: typeof TOKENIZER_NAME;
  tokenizerHash: typeof TOKENIZER_SHA256;
  tokenizerVocabSize: typeof TOKENIZER_VOCAB_SIZE;
  tokenizerStatus: 'bound';
}

export function narrationVersions(
  serializerVersion: typeof SERIALIZER_VERSION | typeof LEGACY_SERIALIZER_VERSION = SERIALIZER_VERSION,
): NarrationVersionSet {
  return {
    projectionVersion: PROJECTION_VERSION,
    serializerVersion,
    legacyProjectionVersion: LEGACY_PROJECTION_VERSION,
    legacySerializerVersion: LEGACY_SERIALIZER_VERSION,
    modelTemplateVersion: MODEL_TEMPLATE_VERSION,
    tokenizerName: TOKENIZER_NAME,
    tokenizerHash: TOKENIZER_SHA256,
    tokenizerVocabSize: TOKENIZER_VOCAB_SIZE,
    tokenizerStatus: 'bound',
  };
}
