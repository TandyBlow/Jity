/** Calibration harness for the independent narration review.
 *
 * Reads a batch file (default: the recorded anchors) and asserts, per case,
 * the findings that must and must not appear. Also writes the full reports so
 * every sentence keeps its evidence record.
 *
 * Env:
 *   NARRATION_QUALITY_BATCH   path to the batch JSON
 *   NARRATION_QUALITY_REPORT  path for the written report JSON
 */
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { describe, expect, test } from 'vitest';
import { reviewNarration } from './review';
import type { DatasetInput } from './scene';
import type { Finding, ReviewOptions, ReviewReport, Severity } from './types';

interface AnchorCase {
  id: string;
  source: string;
  input: DatasetInput;
  text: string;
  options?: ReviewOptions;
  expect?: {
    fact?: string[];
    style?: string[];
    review?: string[];
    forbid?: string[];
    notes?: string;
  };
}

interface Batch {
  version: string;
  genders?: Record<string, { gender: 'male' | 'female' }>;
  cases: AnchorCase[];
}

const batchPath = resolve(process.env.NARRATION_QUALITY_BATCH
  ?? resolve(process.cwd(), '../experiments/narration-quality/review/anchors.json'));
const reportPath = process.env.NARRATION_QUALITY_REPORT
  ? resolve(process.env.NARRATION_QUALITY_REPORT)
  : resolve(process.cwd(), '../.local/narration-quality/anchors-report.json');

const batch = JSON.parse(readFileSync(batchPath, 'utf8')) as Batch;
const genderRegistry = Object.fromEntries(
  Object.entries(batch.genders ?? {}).map(([name, entry]) => [name, entry.gender]),
);

function has(kinds: Iterable<string>, wanted: string): boolean {
  for (const kind of kinds) if (kind === wanted) return true;
  return false;
}

function kindsOf(findings: readonly Finding[], severity: Severity): string[] {
  return findings.filter((entry) => entry.severity === severity).map((entry) => entry.kind);
}

describe('independent review calibration', () => {
  test('every case matches its recorded expectation', () => {
    const reports: ReviewReport[] = [];
    const failures: string[] = [];
    for (const entry of batch.cases) {
      const options: ReviewOptions = { ...(entry.options ?? {}) };
      if (!options.genders) options.genders = genderRegistry;
      const report = reviewNarration({ id: entry.id, input: entry.input, text: entry.text, options });
      reports.push(report);
      const fact = kindsOf(report.findings, 'fact');
      const style = kindsOf(report.findings, 'style');
      const review = kindsOf(report.findings, 'review');
      const expected = entry.expect ?? {};
      for (const kind of expected.fact ?? []) {
        if (!has(fact, kind)) failures.push(`${entry.id}: missing ${kind} (fact has ${[...new Set(fact)].join(', ') || 'none'})`);
      }
      for (const kind of expected.style ?? []) {
        if (!has(style, kind)) failures.push(`${entry.id}: missing ${kind} (style has ${[...new Set(style)].join(', ') || 'none'})`);
      }
      for (const kind of expected.review ?? []) {
        if (!has(review, kind)) failures.push(`${entry.id}: missing ${kind} (review has ${[...new Set(review)].join(', ') || 'none'})`);
      }
      for (const kind of expected.forbid ?? []) {
        if (has(fact, kind) || has(style, kind) || has(review, kind)) failures.push(`${entry.id}: forbidden ${kind} fired`);
      }
      if (expected.fact && expected.fact.length === 0 && fact.length > 0) {
        failures.push(`${entry.id}: expected no fact findings, got ${[...new Set(fact)].join(', ')}`);
      }
    }
    mkdirSync(dirname(reportPath), { recursive: true });
    writeFileSync(reportPath, `${JSON.stringify({
      version: batch.version,
      batch: batchPath,
      reviewer: 'ai-independent-checker-v1',
      generatedAt: new Date().toISOString(),
      cases: reports.map((report) => ({
        id: report.id,
        chars: report.chars,
        counts: report.counts,
        time: report.time,
        mandatory: report.mandatory,
        findings: report.findings,
        sentences: report.sentences,
      })),
    }, null, 2)}\n`);
    expect(failures, failures.join('\n')).toEqual([]);
  }, 120_000);
});
