import { existsSync, readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { renderNarrationInput } from './pipeline';
import { sha256Hex } from './sha256';
import type { NarrationProjection } from './types';

interface RowIndexEntry {
  id: string;
  xProseSha256: string;
  xProseChars: number;
  xProseUtf8Bytes: number;
  xSha256: string;
  legacySha256: string;
  legacyChars: number;
}

interface RowIndex {
  source: {
    commit: string;
    files: Record<string, { expected: string; actual: string; ok: boolean }>;
    versions: Record<string, string>;
  };
  rows: RowIndexEntry[];
}

const root = resolve('src/lib/world-engine/local/narration-input/goldens/runtime-v2');
const index = JSON.parse(readFileSync(join(root, 'train-rows-index.json'), 'utf8')) as RowIndex;
const projections = readFileSync(join(root, 'train-projections.jsonl'), 'utf8').split('\n').filter(Boolean)
  .map((line) => JSON.parse(line) as { id: string; x: NarrationProjection });
const byId = new Map(projections.map((row) => [row.id, row.x]));
const liveDir = process.env.NARRATION_V2_DIR
  ?? 'D:/others/Jity/.local/parallel-local-game/worktrees/10-training/experiments/narration-runtime-v2';
const liveRowsPath = join(liveDir, 'data', 'rows-yuyan-v2.jsonl');
const hasLive = existsSync(liveRowsPath);

function canonical(value: unknown): string {
  if (value === null) return 'null';
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  if (typeof value === 'number') return String(value);
  if (typeof value === 'string') return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  const record = value as Record<string, unknown>;
  return `{${Object.keys(record).sort().map((key) => `${JSON.stringify(key)}:${canonical(record[key])}`).join(',')}}`;
}

describe('199 trained projections from lane 10', () => {
  it('freezes the trained row set', () => {
    expect(index.rows).toHaveLength(199);
    expect(projections).toHaveLength(199);
    expect(index.source.commit).toBe('8f22a086a24f0b1ce030cbaa622862b2b3a16ddc');
    expect(index.source.versions.serializerVersion).toBe('yuyan-prose-result-v2');
    for (const [name, check] of Object.entries(index.source.files)) {
      expect(check.ok, name).toBe(true);
    }
  });

  it('reproduces every trained v2 input byte for byte', () => {
    for (const row of index.rows) {
      const projection = byId.get(row.id);
      expect(projection, row.id).toBeDefined();
      expect(sha256Hex(canonical(projection)), `${row.id} projection`).toBe(row.xSha256);
      const rendered = renderNarrationInput(projection, { checkTokenizer: true });
      expect(rendered.sha256, `${row.id} sha`).toBe(row.xProseSha256);
      expect(rendered.charCount, `${row.id} chars`).toBe(row.xProseChars);
      expect(rendered.utf8Bytes, `${row.id} bytes`).toBe(row.xProseUtf8Bytes);
      expect(rendered.serializerVersion).toBe('yuyan-prose-result-v2');
      expect(rendered.text).not.toContain('【正文】【正文】');
      expect(rendered.text.endsWith('【正文】')).toBe(true);
      const legacy = renderNarrationInput(projection, { model: 'legacy', checkTokenizer: true });
      expect(legacy.sha256, `${row.id} legacy sha`).toBe(row.legacySha256);
      expect(legacy.charCount, `${row.id} legacy chars`).toBe(row.legacyChars);
      expect(legacy.text).not.toContain('【本回合状态】');
    }
  });

  it('closes the 30-row divergence that motivated the parity task', () => {
    // The old 01 sample (sha c4a05f72…) matched the reference only on row-0008.
    // The reference file is sha d699a697…; all of these now match its bytes.
    const ids = [
      'row-0002', 'row-0003', 'row-0004', 'row-0005', 'row-0006', 'row-0007',
      'row-0008', 'row-0009', 'row-0010', 'row-0012', 'row-0013', 'row-0014',
      'row-0020', 'row-0026', 'row-0032', 'row-0038', 'row-0044', 'row-0050',
      'row-0056', 'row-0062', 'row-0068', 'row-0074', 'row-0080', 'row-0086',
      'row-0092', 'row-0095', 'row-0098', 'row-0104', 'row-0110', 'row-0116',
    ];
    const expected = new Map(index.rows.map((row) => [row.id, row.xProseSha256]));
    let identical = 0;
    for (const id of ids) {
      const rendered = renderNarrationInput(byId.get(id), { checkTokenizer: true });
      expect(rendered.sha256, id).toBe(expected.get(id));
      identical += 1;
    }
    expect(identical).toBe(30);
  });

  it('shows the item position and result-block difference on row-0002', () => {
    const projection = byId.get('row-0002')!;
    const v2 = renderNarrationInput(projection, { checkTokenizer: true }).text;
    const legacy = renderNarrationInput(projection, { model: 'legacy', checkTokenizer: true }).text;
    expect(v2).toContain('报架放大镜（位于报刊架后）：');
    expect(legacy).not.toContain('报架放大镜（位于报刊架后）');
    expect(v2).toContain('【本回合状态】');
    expect(legacy).not.toContain('【本回合状态】');
    expect(v2).toContain('报架放大镜（物品）：外貌镜片换过了、黄铜柄磨得发亮。');
  });

  it('renders the no-change row without a result block', () => {
    const projection = byId.get('row-0008')!;
    const v2 = renderNarrationInput(projection, { checkTokenizer: true }).text;
    expect(v2).toContain('这一回合没有结算出变化。');
    expect(v2).not.toContain('【本回合状态】');
  });

  it('renders empty result lists explicitly', () => {
    const projection = byId.get('row-0095')!;
    const v2 = renderNarrationInput(projection, { checkTokenizer: true }).text;
    expect(v2).toContain('柏书言（人物）：外貌（空）。');
  });
});

describe.skipIf(!hasLive)('live lane-10 data cross-check', () => {
  it('matches every stored xProse in the live data file', () => {
    const live = new Map(readFileSync(liveRowsPath, 'utf8').split('\n').filter(Boolean).map((line) => {
      const record = JSON.parse(line) as { id: string; xProse: string };
      return [record.id, record.xProse] as const;
    }));
    expect(live.size).toBe(199);
    for (const row of index.rows) {
      const projection = byId.get(row.id)!;
      const rendered = renderNarrationInput(projection, { checkTokenizer: true });
      expect(rendered.text, row.id).toBe(live.get(row.id));
    }
  });
});
