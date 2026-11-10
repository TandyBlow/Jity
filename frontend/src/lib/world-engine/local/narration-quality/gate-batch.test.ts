/** Batch promotion-gate runner for lanes 11/12 and for 06's dry runs.
 *
 * Set `NARRATION_QUALITY_ROWS` (JSONL: `{"id","input","text","textSource"?}`)
 * and `NARRATION_QUALITY_GATE_REPORT`. Each row goes through `reviewNarration`
 * and `gateNarration`; the report keeps the per-case decision, the reasons and
 * the review count. It is a decision helper, not a quality verdict: a
 * `hold_for_review` case still needs a human/independent reader.
 */
import { describe, expect, it } from 'vitest';
import { readFileSync, writeFileSync } from 'node:fs';
import { reviewNarration } from './review';
import { gateNarration } from './gate';
import type { GatePolicy } from './gate';
import type { DatasetInput } from './scene';
import type { ReviewOptions } from './types';

const ROWS = process.env.NARRATION_QUALITY_ROWS;
const OUT = process.env.NARRATION_QUALITY_GATE_REPORT;
const MIN = process.env.NARRATION_QUALITY_MIN_CHARS ? Number(process.env.NARRATION_QUALITY_MIN_CHARS) : undefined;
const MAX = process.env.NARRATION_QUALITY_MAX_CHARS ? Number(process.env.NARRATION_QUALITY_MAX_CHARS) : undefined;

describe('gate batch', () => {
  it.skipIf(!ROWS || !OUT)('decides accept / hold / regenerate for each row', () => {
    const rows = readFileSync(ROWS!, 'utf8').split('\n').filter((line) => line.trim().length > 0)
      .map((line) => JSON.parse(line) as { id: string; input: DatasetInput; text: string; textSource?: GatePolicy['textSource']; options?: ReviewOptions });
    const cases = rows.map((row) => {
      const report = reviewNarration({ id: row.id, input: row.input, text: row.text, options: row.options ?? {} });
      const policy: GatePolicy = { textSource: row.textSource ?? 'model' };
      if (MIN !== undefined) policy.minChars = MIN;
      if (MAX !== undefined) policy.maxChars = MAX;
      const gate = gateNarration(report, policy);
      return {
        id: row.id,
        chars: report.chars,
        decision: gate.decision,
        reasons: gate.reasons,
        factFindings: gate.factFindings,
        blockingStyles: gate.blockingStyles,
        reviewItems: gate.reviewItems,
        fallbackSuspected: gate.fallbackSuspected,
        perspectiveQualified: report.perspective.qualified,
      };
    });
    writeFileSync(OUT!, `${JSON.stringify({ reviewer: 'ai-independent-checker-v1', rows: cases.length, cases }, null, 2)}\n`, 'utf8');
    expect(cases.length).toBe(rows.length);
  }, 120_000);
});
