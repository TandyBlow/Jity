import { createHash } from 'node:crypto';
import { existsSync, readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { renderNarrationInput } from './pipeline';
import type { NarrationProjection } from './types';

interface GoldenRow {
  id: string;
  x: Omit<NarrationProjection, '本回合状态'>;
  xProse: string;
  xProseSha256: string;
  xProseChars: number;
  xProseUtf8Bytes: number;
}

interface GoldenFile {
  meta: {
    sourceCommit: string;
    sourceFiles: Record<string, string>;
    rowCount: number;
    goldenRowCount: number;
  };
  rows: GoldenRow[];
}

interface ManifestFile {
  meta: GoldenFile['meta'];
  rows: { id: string; xProseSha256: string; xProseChars: number; xProseUtf8Bytes: number }[];
}

const root = resolve('src/lib/world-engine/local/narration-input/goldens');
const golden = JSON.parse(readFileSync(join(root, 'legacy-rows-v1.json'), 'utf8')) as GoldenFile;
const manifest = JSON.parse(readFileSync(join(root, 'legacy-rows-v1-manifest.json'), 'utf8')) as ManifestFile;
const datasetDir = process.env.NARRATION_DATASET_DIR
  ?? 'D:/others/Jity/.local/world-components-worktree/experiments/world-components/narration-dataset-v1';
const liveXy = join(datasetDir, 'rows-xy.jsonl');
const liveProse = join(datasetDir, 'yuyan', 'rows-yuyan.jsonl');
const hasLiveDataset = existsSync(liveXy) && existsSync(liveProse);

function sha256File(path: string): string {
  return createHash('sha256').update(readFileSync(path)).digest('hex');
}

/** The old frozen projection has no result field; the legacy pipeline fills an
 * empty result without changing a single legacy byte. */
function legacyInput(x: GoldenRow['x']): NarrationProjection {
  return x as unknown as NarrationProjection;
}

describe('legacy serializer byte goldens', () => {
  it('reproduces the frozen Python bytes for all representative rows', () => {
    expect(golden.rows).toHaveLength(30);
    expect(golden.meta.rowCount).toBe(199);
    expect(golden.rows.map((row) => row.id)).toEqual(expect.arrayContaining([
      'row-0002', 'row-0006', 'row-0008', 'row-0095',
    ]));
    for (const row of golden.rows) {
      const rendered = renderNarrationInput(legacyInput(row.x), { model: 'legacy' });
      expect(rendered.text, row.id).toBe(row.xProse);
      expect(rendered.utf8Bytes, row.id).toBe(row.xProseUtf8Bytes);
      expect(rendered.charCount, row.id).toBe(row.xProseChars);
      expect(rendered.sha256, row.id).toBe(row.xProseSha256);
      expect(rendered.serializerVersion).toBe('yuyan-prose-legacy-v1');
      expect(rendered.text).not.toContain('【本回合状态】');
    }
  });

  it('has a manifest for every source row', () => {
    expect(manifest.rows).toHaveLength(199);
    expect(new Set(manifest.rows.map((row) => row.id)).size).toBe(199);
    expect(golden.meta.sourceCommit).toBe('1ab6ca791f97529a7bffed1f4837bf81a28badcb');
  });

  it('squashes only the old time-advance space and keeps the rest lossless', () => {
    const row = golden.rows.find((entry) => entry.id === 'row-0006');
    expect(row).toBeDefined();
    const text = renderNarrationInput(legacyInput(row!.x), { model: 'legacy' }).text;
    expect(text).toContain('时间推进8分钟。');
    expect(text).not.toContain('8 分钟');
    expect(text.endsWith('【正文】')).toBe(true);
  });

  it('still drops the item position, which is why the legacy format is frozen', () => {
    const row = golden.rows.find((entry) => entry.id === 'row-0002')!;
    const text = renderNarrationInput(legacyInput(row.x), { model: 'legacy' }).text;
    expect(text).not.toContain('报架放大镜（位于报刊架后）');
    expect(text).toContain('【物品】报架放大镜：');
  });
});

describe.skipIf(!hasLiveDataset)('live narration dataset bytes', () => {
  it('matches every stored xProse and the manifest hashes', () => {
    for (const [file, hash] of Object.entries(manifest.meta.sourceFiles)) {
      const path = file === 'yuyan/rows-yuyan.jsonl'
        ? liveProse
        : join(datasetDir, file);
      expect(sha256File(path), file).toBe(hash);
    }
    const rows = readFileSync(liveXy, 'utf8').split('\n').filter(Boolean).map((line) => JSON.parse(line) as {
      id: string;
      x: GoldenRow['x'];
    });
    const prose = new Map(readFileSync(liveProse, 'utf8').split('\n').filter(Boolean).map((line) => {
      const record = JSON.parse(line) as { id: string; xProse: string };
      return [record.id, record.xProse] as const;
    }));
    expect(rows).toHaveLength(manifest.rows.length);
    for (const [index, row] of rows.entries()) {
      const expected = prose.get(row.id);
      expect(expected, row.id).toBeDefined();
      const rendered = renderNarrationInput(legacyInput(row.x), { model: 'legacy' });
      expect(rendered.text, row.id).toBe(expected);
      const entry = manifest.rows[index];
      expect(entry.id).toBe(row.id);
      expect(rendered.charCount).toBe(entry.xProseChars);
      expect(rendered.utf8Bytes).toBe(entry.xProseUtf8Bytes);
      expect(rendered.sha256).toBe(entry.xProseSha256);
    }
  });
});
