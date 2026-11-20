/** Realization diversity for a candidate pool.
 *
 * The unit of comparison is the TEXT, not the mandatory fact list. Two scenes
 * that both say "A walked from the stairs to the roof" are not diverse when
 * they arrange the same rhythm and details with synonyms. Conversely, sharing
 * every mandatory fact does not make two scenes duplicates: the ordering of
 * environment, action and dialogue, the sentence-length rhythm and the detail
 * layout can differ.
 *
 * Fingerprints:
 *   - surface: character 3-gram set of normalized prose (catches synonyms and
 *     copied clauses);
 *   - structure: ordered sentence tokens (dialogue/narration, length bucket,
 *     clause-count bucket) bigrams (catches the same rhythm);
 *   - details: ordered licensed-entity mentions (catches the same detail
 *     layout even with new wording).
 *
 * The thresholds are frozen in the experiment preregistration. This file is
 * deterministic: same texts and config, same clusters.
 */
import type {
  DiversityConfig, DiversityReport, PairVerdict, RealizationCluster, SampleProfile,
  TextMetrics,
} from './types';

export const DEFAULT_DIVERSITY: DiversityConfig = {
  ngram: 3,
  surfaceNearDuplicate: 0.62,
  containmentDuplicate: 0.8,
  skeletonStructure: 0.85,
  skeletonDetail: 0.75,
  skeletonAligned: 0.42,
  skeletonSurfaceFloor: 0.2,
  edgeDuplicate: 0.78,
  shortTextChars: 40,
  shortTextSurface: 0.45,
  ambiguityBand: 0.05,
  sentenceCountTolerance: 1,
};

const SENTENCE_END = /[。！？!?…]+|\n+/u;
const CLAUSE_END = /[，,、；;：:]/u;
const DIALOGUE = /[「『“"」』”]/u;
const PUNCT = /[\s，,、；;：:。.！？!?…—–\-·"'“”‘’「」『』（）()《》【】[\]]+/gu;
const ZERO_WIDTH = /[\u200b-\u200f\ufeff]/gu;

const cjkLength = (value: string): number => [...value].length;

/** Normalization removes only punctuation, spacing and quote style. It never
 * removes words, so a synonym swap still leaves a different n-gram set (it
 * just overlaps less than a copy). */
export function normalizeProse(text: string): string {
  return text
    .normalize('NFKC')
    .replace(ZERO_WIDTH, '')
    .replace(PUNCT, '')
    .toLowerCase();
}

const meaningfulChars = (sentence: string): number => cjkLength(sentence.normalize('NFKC').replace(PUNCT, ''));

export function splitSentences(text: string): string[] {
  return text.split(SENTENCE_END).map((part) => part.trim()).filter((part) => part.length > 0);
}

function lengthBucket(sentence: string): number {
  const length = cjkLength(sentence);
  if (length <= 8) return 0;
  if (length <= 16) return 1;
  if (length <= 28) return 2;
  if (length <= 48) return 3;
  return 4;
}

function clauseBucket(sentence: string): number {
  const count = sentence.split(CLAUSE_END).length - 1;
  if (count <= 1) return 0;
  if (count <= 3) return 1;
  return 2;
}

function structureToken(sentence: string): string {
  const kind = DIALOGUE.test(sentence) ? 'd' : 'n';
  return `${kind}${lengthBucket(sentence)}${clauseBucket(sentence)}`;
}

function sortedSet(values: Iterable<string>): string[] {
  return [...new Set(values)].sort();
}

export function shinglesOf(text: string, n: number): string[] {
  const chars = [...text];
  if (chars.length === 0) return [];
  if (chars.length <= n) return [chars.join('')];
  const out: string[] = [];
  for (let index = 0; index + n <= chars.length; index += 1) out.push(chars.slice(index, index + n).join(''));
  return sortedSet(out);
}

function sequenceShingles(tokens: readonly string[], n: number): string[] {
  if (tokens.length === 0) return [];
  if (tokens.length <= n) return [tokens.join('|')];
  const out: string[] = [];
  for (let index = 0; index + n <= tokens.length; index += 1) out.push(tokens.slice(index, index + n).join('|'));
  return sortedSet(out);
}

function setSize(set: readonly string[]): number {
  return set.length;
}

export function jaccard(a: readonly string[], b: readonly string[]): number {
  if (a.length === 0 && b.length === 0) return 0;
  const left = new Set(a);
  let intersection = 0;
  for (const value of b) if (left.has(value)) intersection += 1;
  const union = left.size + new Set(b).size - intersection;
  return union === 0 ? 0 : intersection / union;
}

export function containment(inner: readonly string[], outer: readonly string[]): number {
  if (inner.length === 0) return 0;
  const outerSet = new Set(outer);
  let intersection = 0;
  for (const value of inner) if (outerSet.has(value)) intersection += 1;
  return intersection / inner.length;
}

/** Ordered entity mentions. Longest name wins at a position so 天台楼梯间 is
 * not also counted as 天台. */
export function detailTokensOf(normalized: string, licensedEntities: readonly string[]): string[] {
  const names = licensedEntities
    .map((name) => ({ raw: name, normalized: normalizeProse(name) }))
    .filter((entry) => entry.normalized.length >= 2)
    .sort((a, b) => b.normalized.length - a.normalized.length || a.normalized.localeCompare(b.normalized));
  const found: Array<{ at: number; name: string }> = [];
  for (const name of names) {
    let from = 0;
    for (;;) {
      const at = normalized.indexOf(name.normalized, from);
      if (at < 0) break;
      found.push({ at, name: name.normalized });
      from = at + name.normalized.length;
    }
  }
  found.sort((a, b) => a.at - b.at || b.name.length - a.name.length);
  const ordered: string[] = [];
  let lastEnd = -1;
  for (const entry of found) {
    if (entry.at < lastEnd) continue;
    ordered.push(entry.name);
    lastEnd = entry.at + entry.name.length;
  }
  return ordered;
}

export function profileSample(input: {
  id: string;
  seed: number;
  text: string;
  licensedEntities?: readonly string[];
  config?: Partial<DiversityConfig>;
}): SampleProfile {
  const config = { ...DEFAULT_DIVERSITY, ...(input.config ?? {}) };
  const sentences = splitSentences(input.text);
  const normalized = normalizeProse(input.text);
  const dialogueChars = sentences
    .filter((sentence) => DIALOGUE.test(sentence))
    .reduce((sum, sentence) => sum + cjkLength(sentence), 0);
  const totalChars = sentences.reduce((sum, sentence) => sum + cjkLength(sentence), 0);
  return {
    id: input.id,
    seed: input.seed,
    normalized,
    sentences,
    surfaceShingles: shinglesOf(normalized, config.ngram),
    structureTokens: sentences.map(structureToken),
    detailTokens: detailTokensOf(normalized, input.licensedEntities ?? []),
    chars: cjkLength(normalized),
    dialogueRatio: totalChars === 0 ? 0 : dialogueChars / totalChars,
    sentenceLengths: sentences.map(cjkLength),
  };
}

function edgeJaccard(a: string, b: string, n: number): number {
  return jaccard(shinglesOf(normalizeProse(a), n), shinglesOf(normalizeProse(b), n));
}

/** Sentence-aligned paraphrase signal. Each sentence is compared with every
 * sentence of the other text (character bigrams) and the mean best match is
 * taken in both directions. A synonym rewrite of the same sentence order
 * scores well above two different scenes that merely share nouns. */
function alignedSentenceJaccard(a: SampleProfile, b: SampleProfile): number {
  const left = a.sentences.map((sentence) => shinglesOf(normalizeProse(sentence), 2));
  const right = b.sentences.map((sentence) => shinglesOf(normalizeProse(sentence), 2));
  if (left.length === 0 || right.length === 0) return 0;
  const meanBest = (from: string[][], to: string[][]): number =>
    from.reduce((sum, shingles) => {
      let best = 0;
      for (const other of to) best = Math.max(best, jaccard(shingles, other));
      return sum + best;
    }, 0) / from.length;
  return (meanBest(left, right) + meanBest(right, left)) / 2;
}

function near(value: number, threshold: number, band: number): boolean {
  return Math.abs(value - threshold) <= band;
}

export function comparePair(a: SampleProfile, b: SampleProfile, config?: Partial<DiversityConfig>): PairVerdict {
  const cfg = { ...DEFAULT_DIVERSITY, ...(config ?? {}) };
  const surfaceJaccard = jaccard(a.surfaceShingles, b.surfaceShingles);
  const containmentScore = Math.max(
    containment(a.surfaceShingles, b.surfaceShingles),
    containment(b.surfaceShingles, a.surfaceShingles),
  );
  const structureJaccard = jaccard(
    sequenceShingles(a.structureTokens, 2),
    sequenceShingles(b.structureTokens, 2),
  );
  const alignedJaccard = alignedSentenceJaccard(a, b);
  const detailJaccard = a.detailTokens.length && b.detailTokens.length
    ? jaccard(
      sequenceShingles(a.detailTokens, 2),
      sequenceShingles(b.detailTokens, 2),
    )
    : null;
  const openingJaccard = a.sentences.length && b.sentences.length
    ? edgeJaccard(a.sentences[0], b.sentences[0], cfg.ngram)
    : 0;
  const closingJaccard = a.sentences.length && b.sentences.length
    ? edgeJaccard(a.sentences.at(-1) ?? '', b.sentences.at(-1) ?? '', cfg.ngram)
    : 0;

  const reasons: string[] = [];
  if (surfaceJaccard >= cfg.surfaceNearDuplicate) {
    reasons.push(`surface_paraphrase:${surfaceJaccard.toFixed(2)}>=${cfg.surfaceNearDuplicate}`);
  }
  if (containmentScore >= cfg.containmentDuplicate) {
    reasons.push(`contained_rewrite:${containmentScore.toFixed(2)}>=${cfg.containmentDuplicate}`);
  }
  if (a.chars < cfg.shortTextChars && b.chars < cfg.shortTextChars
    && surfaceJaccard >= cfg.shortTextSurface) {
    reasons.push(`short_template:${surfaceJaccard.toFixed(2)}>=${cfg.shortTextSurface}`);
  }
  if (structureJaccard >= cfg.skeletonStructure
    && alignedJaccard >= cfg.skeletonAligned
    && surfaceJaccard >= cfg.skeletonSurfaceFloor
    && (detailJaccard === null || detailJaccard >= cfg.skeletonDetail)) {
    reasons.push(`same_skeleton:structure:${structureJaccard.toFixed(2)}>=${cfg.skeletonStructure}`
      + `,aligned:${alignedJaccard.toFixed(2)}>=${cfg.skeletonAligned}`
      + `,surface:${surfaceJaccard.toFixed(2)}>=${cfg.skeletonSurfaceFloor}`
      + (detailJaccard === null ? ',detail:n/a' : `,detail:${detailJaccard.toFixed(2)}>=${cfg.skeletonDetail}`));
  }
  if (openingJaccard >= cfg.edgeDuplicate && closingJaccard >= cfg.edgeDuplicate
    && Math.abs(a.sentences.length - b.sentences.length) <= cfg.sentenceCountTolerance) {
    reasons.push(`same_opening_and_closing:${openingJaccard.toFixed(2)}/${closingJaccard.toFixed(2)}>=${cfg.edgeDuplicate}`);
  }

  // Any decision metric sitting within the band of its own threshold makes the
  // pair review-worthy. This can over-flag a clearly non-homogeneous pair; it
  // never changes the automatic verdict, and the preregistered review request
  // carries the raw scores for the independent reviewer.
  const ambiguous = [
    near(surfaceJaccard, cfg.surfaceNearDuplicate, cfg.ambiguityBand),
    near(containmentScore, cfg.containmentDuplicate, cfg.ambiguityBand),
    near(structureJaccard, cfg.skeletonStructure, cfg.ambiguityBand),
    near(alignedJaccard, cfg.skeletonAligned, cfg.ambiguityBand),
    near(openingJaccard, cfg.edgeDuplicate, cfg.ambiguityBand),
    near(closingJaccard, cfg.edgeDuplicate, cfg.ambiguityBand),
    detailJaccard !== null && near(detailJaccard, cfg.skeletonDetail, cfg.ambiguityBand),
  ].some(Boolean);

  return {
    a: a.id,
    b: b.id,
    homogeneous: reasons.length > 0,
    reasons,
    surfaceJaccard,
    containment: containmentScore,
    alignedJaccard,
    structureJaccard,
    detailJaccard,
    openingJaccard,
    closingJaccard,
    ambiguous,
  };
}

/** Complete-linkage clustering in caller-provided (seed) order. A candidate
 * joins a cluster only when it is homogeneous to EVERY member, so a chain of
 * mild similarities cannot merge two genuinely different scenes. */
export function clusterProfiles(
  profiles: readonly SampleProfile[],
  config?: Partial<DiversityConfig>,
): RealizationCluster[] {
  const clusters: RealizationCluster[] = [];
  for (const profile of profiles) {
    let joined = false;
    for (const cluster of clusters) {
      const members = cluster.members
        .map((id) => profiles.find((entry) => entry.id === id))
        .filter((entry): entry is SampleProfile => Boolean(entry));
      if (members.every((member) => comparePair(profile, member, config).homogeneous)) {
        cluster.members.push(profile.id);
        joined = true;
        break;
      }
    }
    if (!joined) clusters.push({ id: clusters.length, members: [profile.id] });
  }
  return clusters;
}

/** The preregistered effective repetition. Denominator is always the number of
 * generated samples; it is never replaced by the qualified count. */
export function effectiveRepetition(clusterCount: number, sampleCount: number): number {
  if (sampleCount <= 0) return 0;
  return 1 - clusterCount / sampleCount;
}

export function buildDiversityReport(input: {
  profiles: readonly SampleProfile[];
  qualifiedIds?: readonly string[] | null;
  config?: Partial<DiversityConfig>;
}): DiversityReport {
  const { profiles } = input;
  const pairs: PairVerdict[] = [];
  for (let i = 0; i < profiles.length; i += 1) {
    for (let j = i + 1; j < profiles.length; j += 1) {
      pairs.push(comparePair(profiles[i], profiles[j], input.config));
    }
  }
  const clusters = clusterProfiles(profiles, input.config);
  const qualified = input.qualifiedIds === undefined || input.qualifiedIds === null
    ? null
    : new Set(input.qualifiedIds);
  const qualifiedProfiles = qualified === null
    ? null
    : profiles.filter((profile) => qualified.has(profile.id));
  const qualifiedClusters = qualifiedProfiles === null
    ? null
    : clusters.filter((cluster) => cluster.members.some((id) => qualified?.has(id))).length;
  return {
    sampleCount: profiles.length,
    profiles: [...profiles],
    pairs,
    clusters,
    effectiveRepetition: effectiveRepetition(clusters.length, profiles.length),
    qualifiedClusters,
    qualifiedDistinctClusters: qualifiedProfiles === null
      ? null
      : clusterProfiles(qualifiedProfiles, input.config).length,
    qualifiedCount: qualifiedProfiles === null ? null : qualifiedProfiles.length,
    ambiguousPairs: pairs.filter((pair) => pair.ambiguous).map((pair) => ({
      a: pair.a,
      b: pair.b,
      reasons: pair.reasons,
    })),
  };
}

const FILLER = /^(?:片刻|沉默|空气|气氛|时间|一切|四周|周围)[^。！？]{0,14}(?:过去|安静|凝固|静止|沉重|弥漫|流动|继续|停滞|下来)[^。！？]*$/u;

export function textMetrics(text: string, priorText?: string | null): TextMetrics {
  const sentences = splitSentences(text);
  const normalizedSentences = sentences
    .map((sentence) => normalizeProse(sentence))
    .filter((sentence) => sentence.length >= 4);
  const sentenceCounts = new Map<string, number>();
  for (const sentence of normalizedSentences) {
    sentenceCounts.set(sentence, (sentenceCounts.get(sentence) ?? 0) + 1);
  }
  const repeatedSentences = [...sentenceCounts.values()].filter((count) => count >= 2)
    .reduce((sum, count) => sum + count, 0);
  const clauses = text
    .split(/[。！？!?…；;，,\n]+/u)
    .map((clause) => normalizeProse(clause))
    .filter((clause) => clause.length >= 8);
  const clauseCounts = new Map<string, number>();
  for (const clause of clauses) clauseCounts.set(clause, (clauseCounts.get(clause) ?? 0) + 1);
  const repeatedClauses = [...clauseCounts.values()].filter((count) => count >= 3)
    .reduce((sum, count) => sum + count, 0);
  const empty = sentences.filter((sentence) => {
    const meaningful = meaningfulChars(sentence);
    return meaningful <= 3 || FILLER.test(sentence.trim());
  }).length;
  const surface = shinglesOf(normalizeProse(text), 2);
  const priorEcho = priorText && priorText.trim()
    ? containment(surface, shinglesOf(normalizeProse(priorText), 2))
    : 0;
  const dialogueChars = sentences
    .filter((sentence) => DIALOGUE.test(sentence))
    .reduce((sum, sentence) => sum + cjkLength(sentence), 0);
  const total = sentences.reduce((sum, sentence) => sum + cjkLength(sentence), 0);
  return {
    chars: cjkLength(normalizeProse(text)),
    sentences: sentences.length,
    repeatedSentenceRatio: normalizedSentences.length === 0
      ? 0
      : repeatedSentences / normalizedSentences.length,
    repeatedClauseRatio: clauses.length === 0 ? 0 : repeatedClauses / clauses.length,
    emptySentenceRatio: sentences.length === 0 ? 1 : empty / sentences.length,
    priorEcho,
    dialogueRatio: total === 0 ? 0 : dialogueChars / total,
  };
}

export function setSizeOf(values: readonly string[]): number {
  return setSize(values);
}
