/** Offline analysis for one or more prepared best-of-N batches.
 *
 * It does four separate things and never mixes their verdicts:
 *   1. runs 01's frozen-rubric checker (`reviewNarration`) per raw sample;
 *   2. measures realization diversity with lane 12's module;
 *   3. compares N=1 / N=2 / N=4 arms on the same seeds and cases;
 *   4. writes the evidence and an independent-review request.
 *
 * The reference answer is never read. The checker is mechanical, not human.
 * `pending` findings stay pending; the report never upgrades them.
 *
 * Run from frontend/:
 *   node_modules/.bin/jiti ../experiments/narration-best-of-n/src/analyze.ts \
 *     --batch b01 [--batch b02-generalization]
 */
import { createHash } from 'node:crypto';
import { existsSync, readFileSync, statSync, writeFileSync, readdirSync, mkdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  buildDiversityReport, profileSample, selectCandidate, textMetrics,
} from '../../../frontend/src/lib/world-engine/local/narration-candidates/best-of-n';

const HERE = dirname(fileURLToPath(import.meta.url));
const EXP = resolve(HERE, '..');
const PARALLEL_ROOT = process.env.PARALLEL_ROOT
  ?? 'D:/others/Jity/.local/parallel-local-game';
const CHECKER_DIR = join(PARALLEL_ROOT, 'worktrees/01-input/frontend/src/lib/world-engine/local/narration-quality');
const CHECKER_ENTRY = join(CHECKER_DIR, 'index.ts');

const sha256 = (value: string | Buffer): string => createHash('sha256').update(value).digest('hex');
const nowIso = (): string => new Date().toISOString();
const nowMs = (): number => performance.now();

interface Assessment {
  id: string;
  qualified: boolean | null;
  mandatoryCovered: number;
  mandatoryTotal: number;
  hardIssueKinds: string[];
  detail?: string;
}

interface SampleRow {
  callId: string;
  caseId: string;
  seed: number;
  status: string;
  error?: string | null;
  text: string;
  rawText?: string;
  textSha256?: string;
  finishReason?: string;
  timings?: Record<string, number | null>;
  inputSha256?: string;
}

interface ExpectedRow {
  caseId: string;
  category: string;
  worldFamily: string;
  inputSha256: string;
  input: Record<string, unknown>;
  requiredFacts: Array<Record<string, unknown>>;
  licensedEntities: string[];
  priorTexts: string[];
  viewpoint: string;
  notes: string;
  authors?: Record<string, unknown> | null;
}

interface CheckerFinding {
  kind: string;
  severity: 'fact' | 'style' | 'review';
  sentence: string;
  detail: string;
  basis: string[];
}

interface CheckerReport {
  counts: Record<'fact' | 'style' | 'review', number>;
  mandatory: Array<{ summary: string; expressed: boolean; form: string }>;
  findings: CheckerFinding[];
}

type CheckerModule = {
  reviewNarration: (args: { id: string; input: Record<string, unknown>; text: string }) => CheckerReport;
};

function argValues(name: string): string[] {
  const values: string[] = [];
  process.argv.forEach((value, index) => {
    if (value === name && process.argv[index + 1]) values.push(process.argv[index + 1]);
  });
  return values;
}

function loadJson<T>(path: string): T {
  return JSON.parse(readFileSync(path, 'utf8')) as T;
}

function loadJsonl<T>(path: string): T[] {
  return readFileSync(path, 'utf8')
    .split('\n')
    .filter((line) => line.trim().length > 0)
    .map((line) => JSON.parse(line) as T);
}

function checkerHashes(): { files: Record<string, string>; combined: string } {
  const files: Record<string, string> = {};
  for (const name of readdirSync(CHECKER_DIR).sort()) {
    const path = join(CHECKER_DIR, name);
    if (statSync(path).isFile() && name.endsWith('.ts')) files[name] = sha256(readFileSync(path));
  }
  return { files, combined: sha256(Object.entries(files).map(([name, hash]) => `${name}:${hash}`).join('\n')) };
}

function configFor(batch: string): { caseIds: string[]; seeds: number[]; sharedPack: Record<string, unknown> } {
  return loadJson(join(EXP, 'configs', `${batch}.json`));
}

function preregGuard(): Record<string, unknown> {
  const preregPath = join(EXP, 'preregistration.json');
  const preregBytes = readFileSync(preregPath);
  const expectedPath = join(EXP, 'preregistration.sha256');
  if (!existsSync(expectedPath)) throw new Error('preregistration.sha256 missing; freeze the prereg before analysis');
  const expected = readFileSync(expectedPath, 'utf8').trim().split(/\s+/)[0];
  const actual = sha256(preregBytes);
  if (actual !== expected) throw new Error(`preregistration_sha256_mismatch:${actual}!=${expected}`);
  return JSON.parse(preregBytes.toString('utf8')) as Record<string, unknown>;
}

function classify(seed: number, report: CheckerReport, text: string): {
  decision: 'pass' | 'pending' | 'style_fail' | 'fail';
  factQualified: boolean;
  styleIssueKinds: string[];
  reviewIssueKinds: string[];
  factIssueKinds: string[];
} {
  const factIssueKinds = [...new Set(report.findings.filter((entry) => entry.severity === 'fact').map((entry) => entry.kind))];
  const styleIssueKinds = [...new Set(report.findings.filter((entry) => entry.severity === 'style').map((entry) => entry.kind))];
  const reviewIssueKinds = [...new Set(report.findings.filter((entry) => entry.severity === 'review').map((entry) => entry.kind))];
  const decision = !text.trim() || factIssueKinds.length
    ? 'fail'
    : styleIssueKinds.length
      ? 'style_fail'
      : reviewIssueKinds.length
        ? 'pending'
        : 'pass';
  void seed;
  return {
    decision,
    factQualified: decision !== 'fail',
    factIssueKinds,
    styleIssueKinds,
    reviewIssueKinds,
  };
}

interface CaseAnalysis {
  caseId: string;
  category: string;
  samples: Array<{
    id: string;
    seed: number;
    status: string;
    text: string;
    textSha256: string;
    inputSha256: string;
    finishReason: string | null;
    timings: Record<string, number | null> | null;
    checker: {
      decision: string;
      factQualified: boolean;
      counts: Record<string, number>;
      mandatoryCovered: number;
      mandatoryTotal: number;
      factIssueKinds: string[];
      styleIssueKinds: string[];
      reviewIssueKinds: string[];
      findings: CheckerFinding[];
      mandatory: CheckerReport['mandatory'];
      elapsedMs: number;
    };
    metrics: ReturnType<typeof textMetrics>;
  }>;
  diversity: ReturnType<typeof buildDiversityReport>;
  diversityGate: boolean;
  assessments: Assessment[];
  arms: Array<{
    arm: 1 | 2 | 4;
    selectedId: string | null;
    selectedSeed: number | null;
    selectedFactQualified: boolean;
    selectedPass: boolean;
    selectedCoverage: number;
    selectedRepetition: number;
    selectedPriorEcho: number;
    decision: ReturnType<typeof selectCandidate>;
    callIds: string[];
    callWallMs: number;
    checkerMs: number;
    selectionMs: number;
  }>;
  stopSignals: string[];
}

async function main(): Promise<void> {
  const batches = argValues('--batch');
  if (batches.length === 0) throw new Error('missing_argument:--batch');
  const prereg = preregGuard();
  const checker = await import(CHECKER_ENTRY) as unknown as CheckerModule;
  const checkerIdentity = checkerHashes();
  const moduleHashes = {
    diversity: sha256(readFileSync(join(EXP, '../../frontend/src/lib/world-engine/local/narration-candidates/best-of-n/diversity.ts'))),
    select: sha256(readFileSync(join(EXP, '../../frontend/src/lib/world-engine/local/narration-candidates/best-of-n/select.ts'))),
    analyzer: sha256(readFileSync(fileURLToPath(import.meta.url))),
  };

  const cases: CaseAnalysis[] = [];
  const expectedById = new Map<string, ExpectedRow>();
  const rawInventory: Array<Record<string, unknown>> = [];
  const envs: Record<string, unknown> = {};
  const batchPlans: Record<string, unknown> = {};

  for (const batch of batches) {
    const config = configFor(batch);
    const expectedPath = join(EXP, 'data', batch, 'expected.jsonl');
    const planPath = join(EXP, 'data', batch, 'plan.json');
    const rawPath = join(EXP, 'results', batch, 'raw.jsonl');
    const envPath = join(EXP, 'results', batch, 'env.json');
    if (!existsSync(rawPath)) throw new Error(`raw output missing for ${batch}: ${rawPath}`);
    const expected = new Map(loadJsonl<ExpectedRow>(expectedPath).map((row) => [row.caseId, row]));
    const raw = loadJsonl<SampleRow>(rawPath);
    const plan = loadJson<Record<string, unknown>>(planPath);
    const env = existsSync(envPath) ? loadJson<Record<string, unknown>>(envPath) : { missing: true };
    batchPlans[batch] = plan;
    envs[batch] = env;
    if (env.partial === true) throw new Error(`batch ${batch} is partial; no analysis on a smoke run`);
    const expectedCalls = config.caseIds.length * config.seeds.length;
    if (raw.length !== expectedCalls) {
      throw new Error(`batch ${batch} raw rows ${raw.length} != expected calls ${expectedCalls}`);
    }

    for (const caseId of config.caseIds) {
      const expectedRow = expected.get(caseId);
      if (!expectedRow) throw new Error(`expected row missing:${caseId}`);
      expectedById.set(caseId, expectedRow);
      const rows = raw.filter((row) => row.caseId === caseId);
      const bySeed = new Map<number, SampleRow>();
      const duplicateSeeds: number[] = [];
      for (const row of rows) {
        if (bySeed.has(row.seed)) duplicateSeeds.push(row.seed);
        else bySeed.set(row.seed, row);
      }
      const samples: CaseAnalysis['samples'] = [];
      for (const seed of config.seeds) {
        const row = bySeed.get(seed);
        if (!row) throw new Error(`missing raw sample ${caseId}:s${seed}`);
        if (row.textSha256 && sha256(row.text) !== row.textSha256) {
          throw new Error(`raw text sha mismatch ${caseId}:s${seed}`);
        }
        if (row.inputSha256 && row.inputSha256 !== expectedRow.inputSha256) {
          throw new Error(`raw input sha mismatch ${caseId}:s${seed}`);
        }
        const started = nowMs();
        const report = checker.reviewNarration({ id: `${caseId}:s${seed}`, input: expectedRow.input, text: row.text });
        const checkerMs = nowMs() - started;
        if (report.counts.fact + report.counts.style + report.counts.review !== report.findings.length) {
          throw new Error(`checker count mismatch ${caseId}:s${seed}`);
        }
        const classified = classify(seed, report, row.text);
        const mandatoryCovered = report.mandatory.filter((entry) => entry.expressed).length;
        samples.push({
          id: `${caseId}:s${seed}`,
          seed,
          status: row.status,
          text: row.text,
          textSha256: row.textSha256 ?? sha256(row.text),
          inputSha256: row.inputSha256 ?? expectedRow.inputSha256,
          finishReason: row.finishReason ?? null,
          timings: row.timings ?? null,
          checker: {
            ...classified,
            counts: report.counts,
            mandatoryCovered,
            mandatoryTotal: report.mandatory.length,
            findings: report.findings,
            mandatory: report.mandatory,
            elapsedMs: checkerMs,
          },
          metrics: textMetrics(row.text, expectedRow.priorTexts.join('\n') || null),
        });
      }
      samples.sort((a, b) => a.seed - b.seed);

      const profiles = samples.map((sample) => profileSample({
        id: sample.id,
        seed: sample.seed,
        text: sample.text,
        licensedEntities: expectedRow.licensedEntities,
      }));
      const qualifiedIds = samples.filter((sample) => sample.checker.factQualified).map((sample) => sample.id);
      const diversity = buildDiversityReport({ profiles, qualifiedIds });
      const diversityGate = qualifiedIds.length >= 2
        && (diversity.qualifiedDistinctClusters ?? 0) >= 2;

      const assessments: Assessment[] = samples.map((sample) => ({
        id: sample.id,
        qualified: sample.checker.factQualified,
        mandatoryCovered: sample.checker.mandatoryCovered,
        mandatoryTotal: sample.checker.mandatoryTotal,
        hardIssueKinds: sample.checker.factIssueKinds,
        detail: sample.checker.decision,
      }));

      const arms: CaseAnalysis['arms'] = [];
      const stopSignals: string[] = [];
      if (qualifiedIds.length === 0) stopSignals.push('zero_fact_qualified_candidates');
      if (diversity.effectiveRepetition > 0.8) stopSignals.push('effective_repetition_above_0.80');
      if (duplicateSeeds.length) stopSignals.push(`duplicate_seed_rows:${duplicateSeeds.join(',')}`);

      cases.push({
        caseId,
        category: expectedRow.category,
        samples,
        diversity,
        diversityGate,
        assessments,
        arms,
        stopSignals,
      });
      rawInventory.push({
        batch,
        caseId,
        inputSha256: expectedRow.inputSha256,
        rawRows: rows.length,
        seeds: samples.map((sample) => sample.seed),
      });
    }
  }

  const findingTotals: Record<string, number> = {};
  for (const entry of cases) {
    for (const [kind, count] of Object.entries(findingCountsOf(entry.samples))) {
      findingTotals[kind] = (findingTotals[kind] ?? 0) + count;
    }
  }

  const casesWithDiversityGate = cases.filter((entry) => entry.diversityGate).length;
  const zeroQualifiedCases = cases.filter((entry) => entry.samples.every((sample) => !sample.checker.factQualified)).length;
  // Preregistered gate: best-of-2/4 is only tested after at least two cases
  // have >=2 fact-qualified, non-homogeneous candidates and no case is fully
  // fact-unqualified. Before that, the N arms are not computed at all.
  const armTestGate = {
    allowed: cases.length >= 2 && zeroQualifiedCases === 0 && casesWithDiversityGate >= 2,
    reason: cases.length < 2
      ? 'fewer_than_two_cases'
      : zeroQualifiedCases > 0
        ? `zero_fact_qualified_cases:${zeroQualifiedCases}`
        : casesWithDiversityGate < 2
          ? `diversity_gate_cases:${casesWithDiversityGate}<2`
          : 'gate_passed',
  };
  if (armTestGate.allowed) {
    for (const entry of cases) {
      const expectedRow = expectedById.get(entry.caseId);
      if (!expectedRow) throw new Error(`expected row unavailable for arms:${entry.caseId}`);
      entry.arms = computeArms(entry.samples, entry.assessments, expectedRow);
    }
  }

  const armSummary = [1, 2, 4].map((arm) => {
    const trials = cases.map((entry) => entry.arms.find((candidate) => candidate.arm === arm)).filter(Boolean) as CaseAnalysis['arms'];
    const count = trials.length;
    const rate = (predicate: (value: CaseAnalysis['arms'][number]) => boolean): number =>
      count === 0 ? 0 : trials.filter(predicate).length / count;
    return {
      arm,
      trials: count,
      selectedFactQualifiedRate: rate((trial) => trial.selectedFactQualified),
      selectedPassRate: rate((trial) => trial.selectedPass),
      meanSelectedCoverage: count === 0 ? 0 : trials.reduce((sum, trial) => sum + trial.selectedCoverage, 0) / count,
      meanSelectedRepetition: count === 0 ? 0 : trials.reduce((sum, trial) => sum + trial.selectedRepetition, 0) / count,
      meanSelectedPriorEcho: count === 0 ? 0 : trials.reduce((sum, trial) => sum + trial.selectedPriorEcho, 0) / count,
      meanCallWallMs: count === 0 ? 0 : trials.reduce((sum, trial) => sum + trial.callWallMs, 0) / count,
      meanCheckerMs: count === 0 ? 0 : trials.reduce((sum, trial) => sum + trial.checkerMs, 0) / count,
      meanSelectionMs: count === 0 ? 0 : trials.reduce((sum, trial) => sum + trial.selectionMs, 0) / count,
      totalCalls: count * arm,
    };
  });

  const base = armSummary.find((entry) => entry.arm === 1);
  const betterArms = armSummary.filter((entry) => entry.arm !== 1).filter((entry) => {
    if (!base) return false;
    const higherQualified = entry.selectedFactQualifiedRate > base.selectedFactQualifiedRate;
    const equalQualified = entry.selectedFactQualifiedRate === base.selectedFactQualifiedRate;
    const higherPass = entry.selectedPassRate > base.selectedPassRate;
    const equalPass = entry.selectedPassRate === base.selectedPassRate;
    const higherCoverage = entry.meanSelectedCoverage > base.meanSelectedCoverage;
    const repetitionNotWorse = entry.meanSelectedRepetition <= base.meanSelectedRepetition + 1e-9;
    return higherQualified || (equalQualified && higherPass)
      || (equalQualified && equalPass && higherCoverage && repetitionNotWorse);
  }).map((entry) => entry.arm);
  const benefitStatus = !armTestGate.allowed
    ? 'not_evaluated'
    : betterArms.length > 0 ? 'benefit' : 'no_benefit';
  const benefitReasons: string[] = [];
  if (!armTestGate.allowed) benefitReasons.push(`arm_test_not_allowed:${armTestGate.reason}`);
  if (benefitStatus === 'benefit') benefitReasons.push(`arms_better_than_n1:${betterArms.join(',')}`);
  if (benefitStatus === 'no_benefit' && cases.length >= 2) benefitReasons.push('no_arm_strictly_better_on_preregistered_endpoints');

  const reviewRequest = {
    createdAt: nowIso(),
    requestedBy: '12-best-of-n',
    requestKind: 'independent_sentence_review',
    rubric: {
      owner: '01-input',
      version: 'RUBRIC.md',
      sha256: (prereg.sharedInputPackage as Record<string, string>).rubricSha256,
    },
    reviewerRule: '01 default; 05/03 only after per-sample non-participation; 12 cannot sign its own experiment',
    humanReview: { status: 'pending', reason: 'no real human reading has happened yet' },
    reviewKindOfThisFile: 'request_not_a_review',
    cases: cases.map((entry) => {
      const selectedIds = new Set(entry.arms.map((arm) => arm.selectedId).filter((value): value is string => Boolean(value)));
      const qualifiedUnselected = entry.samples
        .filter((sample) => sample.checker.factQualified && !selectedIds.has(sample.id))
        .sort((a, b) => a.textSha256.localeCompare(b.textSha256))[0];
      const sampleIds = entry.arms.length === 0
        ? new Set(entry.samples.map((sample) => sample.id))
        : new Set([...selectedIds, ...(qualifiedUnselected ? [qualifiedUnselected.id] : [])]);
      return {
        caseId: entry.caseId,
        category: entry.category,
        input: expectedFor(entry.caseId).input,
        requiredFacts: expectedFor(entry.caseId).requiredFacts,
        licensedEntities: expectedFor(entry.caseId).licensedEntities,
        priorTexts: expectedFor(entry.caseId).priorTexts,
        authors: expectedFor(entry.caseId).authors ?? null,
        ambiguousPairs: entry.diversity.ambiguousPairs,
        samples: entry.samples.filter((sample) => sampleIds.has(sample.id)).map((sample) => ({
          id: sample.id,
          seed: sample.seed,
          text: sample.text,
          textSha256: sample.textSha256,
          machineDecision: sample.checker.decision,
          machineFindings: sample.checker.findings,
        })),
        questions: [
          '逐句核对事实、视角、指代与必述项；machine findings 只作待核查声明',
          '同义表达是否真的表达了必述事实，还是仅换了词',
          'ambiguous 对是否应算同一表达',
        ],
      };
    }),
  };

  function expectedFor(caseId: string): ExpectedRow {
    for (const batch of batches) {
      const rows = loadJsonl<ExpectedRow>(join(EXP, 'data', batch, 'expected.jsonl'));
      const found = rows.find((row) => row.caseId === caseId);
      if (found) return found;
    }
    throw new Error(`expected row unavailable for ${caseId}`);
  }

  const report = {
    version: 'best-of-n-analysis-v1',
    createdAt: nowIso(),
    batches,
    preregistration: {
      version: prereg.version,
      sha256: sha256(readFileSync(join(EXP, 'preregistration.json'))),
    },
    checker: {
      module: 'worktrees/01-input/frontend/src/lib/world-engine/local/narration-quality',
      files: checkerIdentity.files,
      combinedSha256: checkerIdentity.combined,
      reviewKind: 'mechanical_checker',
      independent: false,
      note: 'mechanical fact/style/review screen; not a human and not an independent sign-off',
    },
    modules: moduleHashes,
    rawInventory,
    findingTotals,
    env: envs,
    plans: batchPlans,
    cases: cases.map((entry) => ({
      caseId: entry.caseId,
      category: entry.category,
      samples: entry.samples,
      diversity: {
        clusters: entry.diversity.clusters,
        effectiveRepetition: entry.diversity.effectiveRepetition,
        qualifiedCount: entry.diversity.qualifiedCount,
        qualifiedClusters: entry.diversity.qualifiedClusters,
        qualifiedDistinctClusters: entry.diversity.qualifiedDistinctClusters,
        ambiguousPairs: entry.diversity.ambiguousPairs,
        pairs: entry.diversity.pairs,
      },
      diversityGate: entry.diversityGate,
      findingCounts: findingCountsOf(entry.samples),
      arms: entry.arms.map((arm) => ({
        arm: arm.arm,
        selectedId: arm.selectedId,
        selectedSeed: arm.selectedSeed,
        selectedFactQualified: arm.selectedFactQualified,
        selectedPass: arm.selectedPass,
        selectedCoverage: arm.selectedCoverage,
        selectedRepetition: arm.selectedRepetition,
        selectedPriorEcho: arm.selectedPriorEcho,
        callIds: arm.callIds,
        callWallMs: arm.callWallMs,
        checkerMs: arm.checkerMs,
        selectionMs: arm.selectionMs,
        rejected: arm.decision.rejected,
        ranking: arm.decision.ranking,
        verdict: arm.decision.verdict,
        reason: arm.decision.reason,
      })),
      stopSignals: entry.stopSignals,
    })),
    armSummary,
    benefit: {
      status: benefitStatus,
      reasons: benefitReasons,
      betterArms,
      armTestGate,
      cases: cases.length,
      casesWithDiversityGate,
      zeroQualifiedCases,
    },
    stop: {
      stopCurrentScheme: cases.some((entry) => entry.stopSignals.includes('zero_fact_qualified_candidates')),
      effectiveRepetitionAbove80: cases.filter((entry) => entry.diversity.effectiveRepetition > 0.8).map((entry) => entry.caseId),
      note: 'preregistered stop also needs a second comparable experiment without improvement; one batch alone does not expand N',
    },
    cost: {
      perArm: armSummary,
      browserAcceptance: 'not measured here; 09 must measure submit-to-first-fact-checked-readable and whole-turn time, all calls/retries included',
    },
    humanReview: { status: 'pending', reviewer: null, reviewKind: null },
  };

  const outDir = join(EXP, 'results', batches[0] + (batches.length > 1 ? '-plus-' + batches.slice(1).join('+') : ''));
  mkdirSync(outDir, { recursive: true });
  writeFileSync(join(outDir, 'report.json'), `${JSON.stringify(report, null, 2)}\n`, 'utf8');
  writeFileSync(join(outDir, 'review-request.json'), `${JSON.stringify(reviewRequest, null, 2)}\n`, 'utf8');
  writeFileSync(join(outDir, 'report.md'), renderMarkdown(report, cases), 'utf8');
  console.log(JSON.stringify({
    outDir,
    batches,
    cases: cases.length,
    benefit: report.benefit,
    stop: report.stop,
    perCase: cases.map((entry) => ({
      caseId: entry.caseId,
      effectiveRepetition: Number(entry.diversity.effectiveRepetition.toFixed(3)),
      qualified: entry.diversity.qualifiedCount,
      qualifiedDistinctClusters: entry.diversity.qualifiedDistinctClusters,
      clusters: entry.diversity.clusters.length,
      diversityGate: entry.diversityGate,
    })),
  }, null, 2));
}

function findingCountsOf(samples: CaseAnalysis['samples']): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const sample of samples) {
    for (const finding of sample.checker.findings) {
      counts[finding.kind] = (counts[finding.kind] ?? 0) + 1;
    }
  }
  return counts;
}

function computeArms(
  samples: CaseAnalysis['samples'],
  assessments: Assessment[],
  expectedRow: ExpectedRow,
): CaseAnalysis['arms'] {
  const arms: CaseAnalysis['arms'] = [];
  for (const arm of [1, 2, 4] as const) {
    const windowSamples = samples.slice(0, arm);
    const selectionStarted = nowMs();
    const decision = selectCandidate({
      candidates: windowSamples.map((sample) => ({ id: sample.id, seed: sample.seed, text: sample.text })),
      assessments,
      options: {
        priorText: expectedRow.priorTexts.join('\n') || null,
        licensedEntities: expectedRow.licensedEntities,
      },
    });
    const selectionMs = nowMs() - selectionStarted;
    const selected = samples.find((sample) => sample.id === decision.selectedId) ?? null;
    const selectedRank = decision.ranking.find((entry) => entry.id === decision.selectedId);
    arms.push({
      arm,
      selectedId: decision.selectedId,
      selectedSeed: selected?.seed ?? null,
      selectedFactQualified: Boolean(selected?.checker.factQualified),
      selectedPass: selected?.checker.decision === 'pass',
      selectedCoverage: !selectedRank
        ? 0
        : selectedRank.mandatoryTotal === 0
          ? 1
          : selectedRank.mandatoryCovered / selectedRank.mandatoryTotal,
      selectedRepetition: selectedRank
        ? selectedRank.metrics.repeatedSentenceRatio + selectedRank.metrics.repeatedClauseRatio + selectedRank.metrics.emptySentenceRatio
        : 1,
      selectedPriorEcho: selectedRank?.metrics.priorEcho ?? 0,
      decision,
      callIds: windowSamples.map((sample) => sample.id),
      callWallMs: windowSamples.reduce((sum, sample) => sum + (sample.timings?.totalMs ?? 0), 0),
      checkerMs: windowSamples.reduce((sum, sample) => sum + sample.checker.elapsedMs, 0),
      selectionMs,
    });
  }
  return arms;
}

function renderMarkdown(report: Record<string, unknown>, cases: CaseAnalysis[]): string {
  const lines: string[] = [];
  lines.push('# best-of-N 分析报告');
  lines.push('');
  lines.push(`- 生成时间：${report.createdAt}`);
  lines.push(`- 批次：${(report.batches as string[]).join(', ')}`);
  lines.push(`- 预注册 SHA-256：\`${(report.preregistration as Record<string, string>).sha256}\``);
  lines.push(`- 检查器（机械，不是人工）：\`${(report.checker as Record<string, string>).combinedSha256}\``);
  lines.push(`- 收益状态：**${(report.benefit as Record<string, unknown>).status}**`);
  lines.push('');
  lines.push('| case | 有效重复率 1-c/6 | 簇 | 事实合格 | 合格簇 | 同质门 |');
  lines.push('|---|---|---|---|---|---|');
  for (const entry of cases) {
    lines.push(`| ${entry.caseId} | ${entry.diversity.effectiveRepetition.toFixed(3)} | ${entry.diversity.clusters.length} | `
      + `${entry.diversity.qualifiedCount} | ${entry.diversity.qualifiedDistinctClusters} | ${entry.diversityGate} |`);
  }
  lines.push('');
  lines.push('## 发现分类总计（机械检查器）');
  lines.push('');
  lines.push('| kind | count |');
  lines.push('|---|---|');
  for (const [kind, count] of Object.entries((report.findingTotals as Record<string, number>) ?? {}).sort()) {
    lines.push(`| ${kind} | ${count} |`);
  }
  lines.push('');
  lines.push('## 六个原始样本');
  for (const entry of cases) {
    lines.push('');
    lines.push(`### ${entry.caseId} (${entry.category})`);
    lines.push('');
    lines.push('| seed | 判定 | 事实 | 文风 | 待复核 | 必述覆盖 | 首 token ms | 总 ms | 文本 SHA |');
    lines.push('|---|---|---|---|---|---|---|---|---|');
    for (const sample of entry.samples) {
      lines.push(`| ${sample.seed} | ${sample.checker.decision} | ${sample.checker.counts.fact} | ${sample.checker.counts.style} | `
        + `${sample.checker.counts.review} | ${sample.checker.mandatoryCovered}/${sample.checker.mandatoryTotal} | `
        + `${sample.timings?.firstTokenMs ?? 'unknown'} | ${sample.timings?.totalMs == null ? 'unknown' : Math.round(sample.timings.totalMs)} | `
        + `\`${sample.textSha256.slice(0, 12)}\` |`);
    }
  }
  lines.push('');
  lines.push('## 各 arm');
  lines.push('');
  lines.push('| arm | trials | 选中事实合格率 | 选中可读合格率 | 平均覆盖 | 平均重复 | 平均调用墙钟 ms |');
  lines.push('|---|---|---|---|---|---|---|');
  for (const arm of report.armSummary as Array<Record<string, number>>) {
    lines.push(`| N=${arm.arm} | ${arm.trials} | ${(arm.selectedFactQualifiedRate * 100).toFixed(0)}% | `
      + `${(arm.selectedPassRate * 100).toFixed(0)}% | ${arm.meanSelectedCoverage.toFixed(2)} | `
      + `${arm.meanSelectedRepetition.toFixed(2)} | ${Math.round(arm.meanCallWallMs)} |`);
  }
  lines.push('');
  lines.push('## 停止/收益');
  lines.push('');
  lines.push('```json');
  lines.push(JSON.stringify({ benefit: report.benefit, stop: report.stop }, null, 2));
  lines.push('```');
  lines.push('');
  lines.push('## 限制');
  lines.push('');
  lines.push('- 机械检查器不是人工审读；`pending` 不通过。独立复核请求见 `review-request.json`，人工状态 pending。');
  lines.push('- HPC 耗时不是浏览器耗时；60 秒首可读 / 300 秒整回合必须由 09 在同一产品页实测。');
  lines.push('- 本批模型不是浏览器产品权重；产品结论需同条件复测。');
  lines.push('');
  return lines.join('\n');
}

main().catch((error) => {
  console.error(error instanceof Error ? `${error.name}: ${error.message}` : String(error));
  process.exit(1);
});
