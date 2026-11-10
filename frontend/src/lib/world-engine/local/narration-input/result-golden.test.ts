import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { renderResultInput } from './render-result';
import { projectionFromRowX } from './test-fixtures';

interface LegacyGolden {
  rows: { id: string; x: Parameters<typeof projectionFromRowX>[0] }[];
}

interface ResultGolden {
  meta: {
    legacyGolden: string;
    projectionVersion: string;
    serializerVersion: string;
    rowCount: number;
  };
  rows: { id: string; resultText: string; utf8Sha256: string; charCount: number; utf8Bytes: number }[];
}

const root = resolve('src/lib/world-engine/local/narration-input/goldens');
const legacy = JSON.parse(readFileSync(join(root, 'legacy-rows-v1.json'), 'utf8')) as LegacyGolden;
const goldenPath = join(root, 'result-samples-v1.json');

async function build(): Promise<ResultGolden> {
  const rows: ResultGolden['rows'] = [];
  for (const row of legacy.rows) {
    const rendered = renderResultInput(projectionFromRowX(row.x));
    rows.push({
      id: row.id,
      resultText: rendered.text,
      utf8Sha256: await rendered.utf8Sha256,
      charCount: rendered.charCount,
      utf8Bytes: rendered.utf8Bytes,
    });
  }
  return {
    meta: {
      legacyGolden: 'legacy-rows-v1.json',
      projectionVersion: 'narration-projection-v1',
      serializerVersion: 'yuyan-prose-result-v2',
      rowCount: rows.length,
    },
    rows,
  };
}

describe('result serializer golden', () => {
  it('matches the frozen v2 bytes', async () => {
    const actual = await build();
    if (process.env.WRITE_RESULT_GOLDENS === '1') {
      writeFileSync(goldenPath, JSON.stringify(actual, null, 0), 'utf8');
    }
    const expected = JSON.parse(readFileSync(goldenPath, 'utf8')) as ResultGolden;
    expect(expected.meta).toEqual(actual.meta);
    for (const [index, row] of expected.rows.entries()) {
      const got = actual.rows[index];
      expect(got.id, row.id).toBe(row.id);
      expect(got.resultText, row.id).toBe(row.resultText);
      expect(got.utf8Sha256, row.id).toBe(row.utf8Sha256);
      expect(got.charCount, row.id).toBe(row.charCount);
      expect(got.utf8Bytes, row.id).toBe(row.utf8Bytes);
    }
  });

  it('shows the known legacy gaps explicitly in the v2 format', async () => {
    const byId = new Map((await build()).rows.map((row) => [row.id, row]));
    const noChange = byId.get('row-0008')!;
    expect(noChange.resultText).not.toContain('【本回合状态】');
    const emptyAppearance = byId.get('row-0095')!;
    expect(emptyAppearance.resultText).toContain('柏书言（人物）：外貌[]');
    const itemAndMove = byId.get('row-0002')!;
    expect(itemAndMove.resultText).toContain('报架放大镜（物品）：外貌[');
    expect(itemAndMove.resultText).toContain('沈含章（人物）：位置长桌区');
    expect(createHash('sha256').update(itemAndMove.resultText, 'utf8').digest('hex')).toBe(itemAndMove.utf8Sha256);
  });
});
