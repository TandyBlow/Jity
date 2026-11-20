/** Tool: turn records that kept only the rendered prompt string into batch
 * rows for `batch.test.ts`.
 *
 * Set `NARRATION_PARSE_ROWS` (JSONL: `{id, inputText, text}`) and
 * `NARRATION_PARSE_OUT`. Rows that do not round-trip are written to
 * `${out}.rejected` with the parse stage, never guessed at.
 */
import { describe, expect, it } from 'vitest';
import { readFileSync, writeFileSync } from 'node:fs';
import { parseLegacyInput } from './parse-legacy';

const ROWS = process.env.NARRATION_PARSE_ROWS;
const OUT = process.env.NARRATION_PARSE_OUT;

describe('parseLegacyInput batch', () => {
  it.skipIf(!ROWS || !OUT)('converts stored prompt strings into dataset rows', () => {
    const lines = readFileSync(ROWS!, 'utf8').split('\n').filter((line) => line.trim().length > 0);
    const accepted: string[] = [];
    const rejected: string[] = [];
    for (const line of lines) {
      const row = JSON.parse(line) as { id: string; inputText: string; text: string; textSource?: string };
      const input = parseLegacyInput(row.inputText);
      if (!input) {
        rejected.push(JSON.stringify({ id: row.id, reason: 'parse_or_roundtrip_failed' }));
        continue;
      }
      accepted.push(JSON.stringify({ id: row.id, input, text: row.text, textSource: row.textSource ?? 'model' }));
    }
    writeFileSync(OUT!, accepted.join('\n') + (accepted.length ? '\n' : ''), 'utf8');
    writeFileSync(`${OUT!}.rejected`, rejected.join('\n') + (rejected.length ? '\n' : ''), 'utf8');
    expect(accepted.length + rejected.length).toBe(lines.length);
  });
});
