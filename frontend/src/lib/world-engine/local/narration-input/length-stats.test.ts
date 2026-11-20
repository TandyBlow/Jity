import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import type { InitialState } from '../../types';
import { buildInitialState } from '../state';
import { projectNarrationInput } from './project';
import { renderResultInput } from './render-result';
import { projectionFromRowX } from './test-fixtures';

const datasetDir = process.env.NARRATION_DATASET_DIR
  ?? 'D:/others/Jity/.local/world-components-worktree/experiments/world-components/narration-dataset-v1';
const liveXy = join(datasetDir, 'rows-xy.jsonl');
const hasLiveDataset = existsSync(liveXy);
const goldenPath = resolve('src/lib/world-engine/local/narration-input/goldens/result-length-stats-v1.json');

function percentile(sorted: number[], fraction: number): number {
  return sorted[Math.max(0, Math.ceil(fraction * sorted.length) - 1)];
}

describe.skipIf(!hasLiveDataset)('result-v2 length distribution', () => {
  it('records the measured distribution for the 199 real rows', async () => {
    const rows = readFileSync(liveXy, 'utf8').split('\n').filter(Boolean).map((line) => JSON.parse(line) as {
      id: string;
      x: Parameters<typeof projectionFromRowX>[0];
    });
    const measured = rows.map((row) => {
      const rendered = renderResultInput(projectionFromRowX(row.x));
      return { id: row.id, chars: rendered.charCount, bytes: rendered.utf8Bytes };
    });
    const chars = measured.map((row) => row.chars).sort((a, b) => a - b);
    const bytes = measured.map((row) => row.bytes).sort((a, b) => a - b);
    const stats = {
      version: 'result-length-stats-v1',
      serializerVersion: 'yuyan-prose-result-v2',
      population: 'rows-xy.jsonl',
      rowCount: measured.length,
      chars: { min: chars[0], p50: percentile(chars, 0.5), p75: percentile(chars, 0.75), max: chars.at(-1) },
      utf8Bytes: { min: bytes[0], p50: percentile(bytes, 0.5), p75: percentile(bytes, 0.75), max: bytes.at(-1) },
      rows: measured,
      note: 'Character counts are Unicode code points, matching Python len. Tokenizer counts must be measured with the actual vocabulary.',
    };
    if (process.env.WRITE_LENGTH_STATS === '1') {
      writeFileSync(goldenPath, JSON.stringify(stats, null, 0), 'utf8');
    }
    const expected = JSON.parse(readFileSync(goldenPath, 'utf8'));
    expect(stats).toEqual(expected);
    expect(stats.rowCount).toBe(199);
    expect(stats.chars.max).toBeGreaterThan(stats.chars.p75);
  });

  it('records the free-day opening length without inventing a result block', () => {
    const raw = JSON.parse(readFileSync(resolve('public/worlds/dragon-raja-free-day.world.json'), 'utf8')) as {
      initial: InitialState;
    };
    const before = buildInitialState(raw.initial);
    const timeAdvance = { boundary: 'elapsed' as const, duration: { amount: 1, unit: 'minute' as const } };
    const result = projectNarrationInput({ before, after: before, delta: {}, timeAdvance, viewpointId: 'lu' });
    const rendered = renderResultInput(result.projection);
    expect(rendered.text).not.toContain('【本回合状态】');
    expect(rendered.charCount).toBeGreaterThan(300);
    expect(rendered.utf8Bytes).toBeGreaterThan(rendered.charCount);
  });
});
