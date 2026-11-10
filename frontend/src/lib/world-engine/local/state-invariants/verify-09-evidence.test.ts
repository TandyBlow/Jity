/** Read-only verification of 09's real product turn records.
 *
 * Normal test runs skip this file. 09 (or a reviewer) points it at one JSON
 * file or a directory of JSON files:
 *
 *   WORLD_STATE_EVIDENCE=.../09-turns.json npx vitest run \
 *     src/lib/world-engine/local/state-invariants/verify-09-evidence.test.ts --maxWorkers=1
 *
 * The test prints a JSON report per record and fails if any record violates
 * the replay/chain invariants. It never writes state and never treats a
 * hand-written state as a game settlement. */
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import {
  verifyDisplayHistory, verifySessionSnapshot, verifyTurnEntry, verifyVisibleAcceptance, type InvariantReport,
} from './index';

const evidencePath = process.env.WORLD_STATE_EVIDENCE;

function filesAt(path: string): string[] {
  const absolute = resolve(path);
  const stat = statSync(absolute);
  if (stat.isFile()) return [absolute];
  return readdirSync(absolute)
    .filter((name) => name.toLowerCase().endsWith('.json'))
    .sort()
    .map((name) => join(absolute, name));
}

function entriesOf(document: unknown): unknown[] {
  if (Array.isArray(document)) return document;
  if (!document || typeof document !== 'object') return [document];
  const record = document as Record<string, unknown>;
  for (const key of ['turns', 'sessions', 'records', 'snapshots', 'evidence']) {
    if (Array.isArray(record[key])) return record[key] as unknown[];
  }
  return [document];
}

function labelFor(document: unknown, index: number): string {
  if (document && typeof document === 'object') {
    const record = document as Record<string, unknown>;
    for (const key of ['turnId', 'id', 'roundId', 'sessionId', 'worldId']) {
      if (typeof record[key] === 'string') return `${record[key]}`;
    }
  }
  return `entry-${index + 1}`;
}

function snapshotValue(entry: unknown): unknown | null {
  if (!entry || typeof entry !== 'object') return null;
  const record = entry as Record<string, unknown>;
  return record.snapshot ?? record.snapshotAfter ?? record.snapshotBefore ?? record.transport ?? record.record ?? null;
}

function addDisplayReport(entry: unknown, report: InvariantReport): InvariantReport {
  const snapshot = snapshotValue(entry);
  if (snapshot == null) return report;
  const display = verifyDisplayHistory(snapshot);
  for (const error of display.errors) report.errors.push({ ...error, detail: `display: ${error.detail}` });
  for (const warning of display.warnings) report.warnings.push({ ...warning, detail: `display: ${warning.detail}` });
  report.ok = report.errors.length === 0;
  return report;
}

async function verifyDocument(document: unknown): Promise<{ label: string; report: InvariantReport }[]> {
  const entries = entriesOf(document);
  const results: { label: string; report: InvariantReport }[] = [];
  const visibleOnly: unknown[] = [];
  for (let index = 0; index < entries.length; index += 1) {
    const entry = entries[index];
    // 09's acceptance JSON stores page-visible before/after summaries, not a
    // transport snapshot. Only entries with a replay anchor go through the
    // full verifier; the rest are checked for visible continuity below.
    const record = entry && typeof entry === 'object' ? entry as Record<string, unknown> : null;
    const before = record?.before ?? record?.stateBefore;
    const point = record?.point ?? record?.delta;
    const hasReplayAnchor = Boolean(record && (record.snapshot != null || record.snapshotAfter != null
      || record.snapshotBefore != null || record.transport != null || record.record != null))
      || (Boolean(before) && typeof before === 'object' && Boolean(point) && typeof point === 'object');
    if (!hasReplayAnchor) {
      visibleOnly.push(entry);
      continue;
    }
    const report = await verifyTurnEntry(entry);
    if (report.errors.length === 0 && report.points === 0 && report.replayDigest == null) {
      // A snapshot envelope was not present; try the envelope itself.
      const fallback = addDisplayReport(entry, await verifySessionSnapshot(entry));
      results.push({ label: labelFor(entry, index), report: fallback });
    } else {
      results.push({ label: labelFor(entry, index), report: addDisplayReport(entry, report) });
    }
  }
  if (visibleOnly.length > 0) {
    const visible = verifyVisibleAcceptance(visibleOnly);
    results.push({
      label: 'visible-summary',
      report: {
        ok: visible.ok,
        worldId: null,
        version: null,
        points: 0,
        headPointId: null,
        rootDigest: null,
        headDigest: null,
        replayDigest: null,
        errors: visible.errors,
        warnings: visible.warnings,
      },
    });
  }
  return results;
}

describe.skipIf(!evidencePath)('09 real product evidence (read-only)', () => {
  it('replays every recorded turn and reports any continuity violation', async () => {
    const all: { file: string; label: string; report: InvariantReport }[] = [];
    for (const file of filesAt(evidencePath!)) {
      const document = JSON.parse(readFileSync(file, 'utf8')) as unknown;
      for (const result of await verifyDocument(document)) {
        all.push({ file, ...result });
      }
    }
    console.log(JSON.stringify(all.map((item) => ({
      file: item.file,
      label: item.label,
      ok: item.report.ok,
      worldId: item.report.worldId,
      version: item.report.version,
      points: item.report.points,
      errors: item.report.errors,
      warnings: item.report.warnings,
    })), null, 2));
    expect(all.length).toBeGreaterThan(0);
    const bad = all.filter((item) => !item.report.ok);
    expect(bad, JSON.stringify(bad.map((item) => ({
      file: item.file, label: item.label, errors: item.report.errors,
    })), null, 2)).toEqual([]);
  });
});
