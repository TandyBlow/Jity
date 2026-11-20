/** Cross-turn review for a real play sequence.
 *
 * Env:
 *   NARRATION_QUALITY_SEQUENCE  JSONL of {groupId, turn, input, text, textSource?}
 *   NARRATION_QUALITY_SEQUENCE_REPORT  output JSON path
 *   NARRATION_QUALITY_SEQUENCE_MAX_CONFLICTS  when set, assert the conflict count
 *
 * Turns are grouped by groupId, sorted by turn, and every turn is also reviewed
 * sentence by sentence, so a conflict can be traced back to the sentence.
 */
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { describe, expect, test } from 'vitest';
import { reviewNarration } from './review';
import type { DatasetInput } from './scene';
import { reviewSequence, type TurnRecord } from './sequence';

interface Row {
  groupId: string;
  turn: number;
  input: DatasetInput;
  text: string;
  textSource?: 'model' | 'program_fallback' | 'mixed';
}

const rowsPath = process.env.NARRATION_QUALITY_SEQUENCE;
const reportPath = process.env.NARRATION_QUALITY_SEQUENCE_REPORT
  ? resolve(process.env.NARRATION_QUALITY_SEQUENCE_REPORT)
  : resolve(process.cwd(), '../.local/narration-quality/sequence-report.json');
const maxConflicts = process.env.NARRATION_QUALITY_SEQUENCE_MAX_CONFLICTS
  ? Number(process.env.NARRATION_QUALITY_SEQUENCE_MAX_CONFLICTS)
  : null;

describe.skipIf(!rowsPath)('sequence review batch', () => {
  test('review every turn and every cross-turn check', () => {
    const rows = readFileSync(rowsPath as string, 'utf8').split(/\r?\n/u).filter(Boolean)
      .map((line) => JSON.parse(line) as Row);
    const groups = new Map<string, Row[]>();
    for (const row of rows) {
      const list = groups.get(row.groupId) ?? [];
      list.push(row);
      groups.set(row.groupId, list);
    }

    const sequences = [...groups.entries()].map(([groupId, list]) => {
      const turns = list.map((row) => ({
        groupId,
        turn: row.turn,
        input: row.input,
        text: row.text,
        textSource: row.textSource,
      })) as TurnRecord[];
      const report = reviewSequence(turns);
      const perTurn = turns.map((turn) => {
        const single = reviewNarration({ id: `${groupId}#${turn.turn}`, input: turn.input, text: turn.text });
        return {
          turn: turn.turn,
          textSource: turn.textSource ?? null,
          factFindings: single.counts.fact,
          blockingStyles: single.blockingStyles,
          reviewItems: single.counts.review,
          fallbackSuspected: single.fallbackSuspicion.suspected,
        };
      });
      return { groupId, report, perTurn };
    });

    const conflicts = sequences.reduce((sum, entry) => sum + entry.report.counts.conflict, 0);
    mkdirSync(dirname(reportPath), { recursive: true });
    writeFileSync(reportPath, `${JSON.stringify({
      reviewer: 'ai-independent-checker-v1',
      generatedAt: new Date().toISOString(),
      groups: sequences.length,
      turns: rows.length,
      conflicts,
      sequences,
      disclaimer: 'Automated cross-turn review only. No human read, no product acceptance. Undetermined items are not passes.',
    }, null, 2)}\n`);

    if (maxConflicts !== null) {
      expect(conflicts, 'cross-turn conflicts above the ceiling').toBeLessThanOrEqual(maxConflicts);
    }
  }, 120_000);
});
