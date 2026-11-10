/** Batch review for whole corpora.
 *
 * Env:
 *   NARRATION_QUALITY_ROWS    JSONL with {id, input, text, gold?}
 *   NARRATION_QUALITY_REPORT  output JSON path
 *   NARRATION_QUALITY_MAX_FACTS  when set, assert the fact-finding count
 *                                (used to keep the human gold at zero)
 */
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { describe, expect, test } from 'vitest';
import { reviewNarration } from './review';
import { genderOptions } from './genders';
import type { DatasetInput } from './scene';

interface Row {
  id: string;
  input: DatasetInput;
  text: string;
  genders?: Record<string, 'male' | 'female'>;
  /** Provenance of the text. Program fallback is never model prose. */
  textSource?: 'model' | 'program_fallback' | 'mixed' | 'unknown';
}

const rowsPath = process.env.NARRATION_QUALITY_ROWS;
const reportPath = process.env.NARRATION_QUALITY_REPORT
  ? resolve(process.env.NARRATION_QUALITY_REPORT)
  : resolve(process.cwd(), '../.local/narration-quality/batch-report.json');
const maxFacts = process.env.NARRATION_QUALITY_MAX_FACTS
  ? Number(process.env.NARRATION_QUALITY_MAX_FACTS)
  : null;

describe.skipIf(!rowsPath)('corpus review batch', () => {
  test('review every row and report', () => {
    const rows = readFileSync(rowsPath as string, 'utf8').split(/\r?\n/u).filter(Boolean)
      .map((line) => JSON.parse(line) as Row);
    const reports = rows.map((row) => {
      const report = reviewNarration({
        id: row.id,
        input: row.input,
        text: row.text,
        options: { genders: row.genders ?? genderOptions() },
      });
      return { ...report, textSource: row.textSource ?? null };
    });
    mkdirSync(dirname(reportPath), { recursive: true });
    writeFileSync(reportPath, `${JSON.stringify({
      reviewer: 'ai-independent-checker-v1',
      generatedAt: new Date().toISOString(),
      rows: rows.length,
      rowsWithFacts: reports.filter((report) => report.counts.fact > 0).length,
      factFindings: reports.reduce((sum, report) => sum + report.counts.fact, 0),
      styleFindings: reports.reduce((sum, report) => sum + report.counts.style, 0),
      reviewItems: reports.reduce((sum, report) => sum + report.counts.review, 0),
      cases: reports,
    }, null, 2)}\n`);
    if (maxFacts !== null) {
      const bad = reports.filter((report) => report.counts.fact > maxFacts);
      expect(bad.map((report) => ({ id: report.id, facts: report.findings.filter((entry) => entry.severity === 'fact') })), 'rows above the fact ceiling').toEqual([]);
    }
  }, 120_000);
});
