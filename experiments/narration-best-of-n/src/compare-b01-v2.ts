/** Side-by-side comparison of two single-case best-of-N reports.
 *
 * This is NOT a pooled diversity run: v1 and v2 use different prompts, so their
 * samples must never be clustered together. It only lines up the same seed and
 * reports each side's fact/style/review verdict, clusters, repetition, cost and
 * the v2 qualification gate. No model call and no reference answer.
 *
 *   node_modules/.bin/jiti src/compare-b01-v2.ts \
 *     --left results/b01/report.json --right results/b01-template-v2/report.json \
 *     --out results/b01-vs-v2
 */
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const EXP = resolve(HERE, '..');
const sha256 = (value: string | Buffer): string => createHash('sha256').update(value).digest('hex');

interface SampleView {
  seed: number;
  status: string;
  text: string;
  textSha256: string;
  checker: {
    decision: string;
    factQualified: boolean;
    counts: Record<string, number>;
    mandatoryCovered: number;
    mandatoryTotal: number;
    factIssueKinds: string[];
    styleIssueKinds: string[];
    reviewIssueKinds: string[];
  };
  timings: Record<string, number | null> | null;
}

interface CaseView {
  caseId: string;
  samples: SampleView[];
  diversity: {
    clusters: Array<{ members: string[] }>;
    effectiveRepetition: number;
    qualifiedCount: number | null;
    qualifiedDistinctClusters: number | null;
  };
  findingCounts: Record<string, number>;
}

interface ReportView {
  version: string;
  createdAt: string;
  batches: string[];
  preregistration: { sha256: string };
  checker: { combinedSha256: string };
  cases: CaseView[];
  env: Record<string, { runWallMs?: number; loadMs?: number }>;
}

function arg(name: string): string {
  const index = process.argv.indexOf(name);
  if (index < 0 || !process.argv[index + 1]) throw new Error(`missing_argument:${name}`);
  return process.argv[index + 1];
}

function load(path: string): ReportView {
  return JSON.parse(readFileSync(path, 'utf8')) as ReportView;
}

function sampleOf(report: ReportView, seed: number): SampleView | null {
  for (const entry of report.cases) {
    const found = entry.samples.find((sample) => sample.seed === seed);
    if (found) return found;
  }
  return null;
}

function main(): void {
  const leftPath = resolve(process.cwd(), arg('--left'));
  const rightPath = resolve(process.cwd(), arg('--right'));
  if (!existsSync(rightPath)) throw new Error(`right report missing: ${rightPath}`);
  const left = load(leftPath);
  const right = load(rightPath);
  const leftCase = left.cases[0];
  const rightCase = right.cases[0];
  if (!leftCase || !rightCase) throw new Error('one report has no case');
  if (leftCase.caseId !== rightCase.caseId) throw new Error('reports are not the same case');

  const seeds = [...new Set([...leftCase.samples, ...rightCase.samples].map((sample) => sample.seed))]
    .sort((a, b) => a - b);
  const rows = seeds.map((seed) => {
    const a = sampleOf(left, seed);
    const b = sampleOf(right, seed);
    return {
      seed,
      left: a ? {
        decision: a.checker.decision,
        factQualified: a.checker.factQualified,
        chars: [...a.text].length,
        coverage: `${a.checker.mandatoryCovered}/${a.checker.mandatoryTotal}`,
        counts: a.checker.counts,
        factIssueKinds: a.checker.factIssueKinds,
        styleIssueKinds: a.checker.styleIssueKinds,
        firstTokenMs: a.timings?.firstTokenMs ?? null,
        totalMs: a.timings?.totalMs ?? null,
        textSha256: a.textSha256,
      } : null,
      right: b ? {
        decision: b.checker.decision,
        factQualified: b.checker.factQualified,
        chars: [...b.text].length,
        coverage: `${b.checker.mandatoryCovered}/${b.checker.mandatoryTotal}`,
        counts: b.checker.counts,
        factIssueKinds: b.checker.factIssueKinds,
        styleIssueKinds: b.checker.styleIssueKinds,
        firstTokenMs: b.timings?.firstTokenMs ?? null,
        totalMs: b.timings?.totalMs ?? null,
        textSha256: b.textSha256,
      } : null,
    };
  });

  const rightQualified = rightCase.samples.filter((sample) => sample.checker.factQualified).length;
  const rightDistinct = rightCase.diversity.qualifiedDistinctClusters ?? 0;
  const v2Gate = rightQualified >= 2 && rightDistinct >= 2;
  const wall = (report: ReportView): number | null => {
    const env = Object.values(report.env)[0];
    return typeof env?.runWallMs === 'number' ? env.runWallMs : null;
  };

  const result = {
    createdAt: new Date().toISOString(),
    caseId: leftCase.caseId,
    left: {
      report: leftPath,
      reportSha256: sha256(readFileSync(leftPath)),
      batches: left.batches,
      preregistrationSha256: left.preregistration.sha256,
      checkerSha256: left.checker.combinedSha256,
      clusters: leftCase.diversity.clusters.length,
      effectiveRepetition: leftCase.diversity.effectiveRepetition,
      qualifiedCount: leftCase.diversity.qualifiedCount,
      qualifiedDistinctClusters: leftCase.diversity.qualifiedDistinctClusters,
      findingCounts: leftCase.findingCounts,
      runWallMs: wall(left),
    },
    right: {
      report: rightPath,
      reportSha256: sha256(readFileSync(rightPath)),
      batches: right.batches,
      preregistrationSha256: right.preregistration.sha256,
      checkerSha256: right.checker.combinedSha256,
      clusters: rightCase.diversity.clusters.length,
      effectiveRepetition: rightCase.diversity.effectiveRepetition,
      qualifiedCount: rightCase.diversity.qualifiedCount,
      qualifiedDistinctClusters: rightCase.diversity.qualifiedDistinctClusters,
      findingCounts: rightCase.findingCounts,
      runWallMs: wall(right),
    },
    delta: {
      qualifiedCount: (rightCase.diversity.qualifiedCount ?? 0) - (leftCase.diversity.qualifiedCount ?? 0),
      clusters: rightCase.diversity.clusters.length - leftCase.diversity.clusters.length,
      effectiveRepetition: rightCase.diversity.effectiveRepetition - leftCase.diversity.effectiveRepetition,
    },
    v2Gate: {
      allowed: v2Gate,
      reason: v2Gate
        ? 'right has >=2 fact-qualified candidates in >=2 realization clusters'
        : `right qualified=${rightQualified}, qualifiedDistinctClusters=${rightDistinct}; needs >=2 and >=2`,
    },
    rows,
    note: 'Two different prompts; samples are never pooled or clustered across columns. No reference answer was read. Mechanical checker, not human review.',
  };

  const outDir = resolve(process.cwd(), arg('--out'));
  mkdirSync(outDir, { recursive: true });
  writeFileSync(join(outDir, 'compare.json'), `${JSON.stringify(result, null, 2)}\n`, 'utf8');

  const lines: string[] = [];
  lines.push(`# ${leftCase.caseId}: v1 vs v2`);
  lines.push('');
  lines.push(`- left: \`${left.batches.join(',')}\` prereg \`${left.preregistration.sha256.slice(0, 12)}\``);
  lines.push(`- right: \`${right.batches.join(',')}\` prereg \`${right.preregistration.sha256.slice(0, 12)}\``);
  lines.push(`- v2 gate: **${v2Gate ? 'pass' : 'not passed'}** (${result.v2Gate.reason})`);
  lines.push('');
  lines.push('| seed | v1 decision | v2 decision | v1 chars | v2 chars | v1 coverage | v2 coverage | v1 fact kinds | v2 fact kinds |');
  lines.push('|---|---|---|---|---|---|---|---|---|');
  for (const row of rows) {
    lines.push(`| ${row.seed} | ${row.left?.decision ?? '-'} | ${row.right?.decision ?? '-'} | `
      + `${row.left?.chars ?? '-'} | ${row.right?.chars ?? '-'} | ${row.left?.coverage ?? '-'} | ${row.right?.coverage ?? '-'} | `
      + `${row.left?.factIssueKinds.join('+') ?? '-'} | ${row.right?.factIssueKinds.join('+') ?? '-'} |`);
  }
  lines.push('');
  lines.push('| metric | v1 | v2 |');
  lines.push('|---|---|---|');
  lines.push(`| clusters | ${leftCase.diversity.clusters.length} | ${rightCase.diversity.clusters.length} |`);
  lines.push(`| 1 - clusters/6 | ${leftCase.diversity.effectiveRepetition.toFixed(3)} | ${rightCase.diversity.effectiveRepetition.toFixed(3)} |`);
  lines.push(`| fact-qualified | ${leftCase.diversity.qualifiedCount} | ${rightCase.diversity.qualifiedCount} |`);
  lines.push(`| qualified distinct clusters | ${leftCase.diversity.qualifiedDistinctClusters} | ${rightCase.diversity.qualifiedDistinctClusters} |`);
  lines.push(`| whole-run wall ms | ${result.left.runWallMs ?? 'unknown'} | ${result.right.runWallMs ?? 'unknown'} |`);
  lines.push('');
  lines.push('No reference answer was read. Mechanical checker only; independent human review is pending.');
  lines.push('');
  writeFileSync(join(outDir, 'compare.md'), lines.join('\n'), 'utf8');
  console.log(JSON.stringify({
    outDir,
    v2Gate: result.v2Gate,
    left: result.left,
    right: result.right,
    delta: result.delta,
  }, null, 2));
}

main();
