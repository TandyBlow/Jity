/** N=1 failure diagnosis against 01's CURRENT checker.
 *
 * This does NOT re-run the model, does not change the b01 report/preregistration
 * and does not make a quality claim. It answers a narrow question: did 01's
 * newer checker start detecting the concrete failures the six frozen b01 texts
 * already contain? The report file keeps the pinned checker used for the
 * original comparison; this diagnosis is a separate, clearly-labelled view.
 *
 *   node_modules/.bin/jiti src/check-current.ts
 */
import { createHash } from 'node:crypto';
import { mkdirSync, readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const EXP = resolve(HERE, '..');
const PARALLEL_ROOT = process.env.PARALLEL_ROOT
  ?? 'D:/others/Jity/.local/parallel-local-game';
const CHECKER_DIR = join(PARALLEL_ROOT, 'worktrees/01-input/frontend/src/lib/world-engine/local/narration-quality');
const OUT = join(EXP, 'results/b01');

const sha256 = (value: string | Buffer): string => createHash('sha256').update(value).digest('hex');
const readJsonl = <T>(path: string): T[] => readFileSync(path, 'utf8')
  .split(/\r?\n/u).filter(Boolean).map((line) => JSON.parse(line) as T);

interface RawRow {
  seed: number;
  text: string;
  caseId: string;
}

interface ExpectedRow {
  caseId: string;
  input: Record<string, unknown>;
}

interface Finding {
  severity: 'fact' | 'style' | 'review';
  kind: string;
  sentence: string;
  detail?: string;
}

interface CheckerReport {
  findings: Finding[];
  mandatory: Array<{ expressed: boolean; summary?: string }>;
}

function checkerHashes(): { files: Record<string, string>; combined: string } {
  const files: Record<string, string> = {};
  for (const name of readdirSync(CHECKER_DIR).sort()) {
    const path = join(CHECKER_DIR, name);
    if (statSync(path).isFile() && name.endsWith('.ts')) files[name] = sha256(readFileSync(path));
  }
  const combined = sha256(Object.entries(files).map(([name, hash]) => `${name}:${hash}`).join('\n'));
  return { files, combined };
}

function kinds(findings: Finding[], severity: Finding['severity']): string[] {
  return [...new Set(findings.filter((finding) => finding.severity === severity).map((finding) => finding.kind))];
}

async function main(): Promise<void> {
  const expected = readJsonl<ExpectedRow>(join(EXP, 'data/b01/expected.jsonl'));
  const raw = readJsonl<RawRow>(join(EXP, 'results/b01/raw.jsonl'));
  const byCase = new Map(expected.map((row) => [row.caseId, row]));
  const checker = await import(pathToFileURL(join(CHECKER_DIR, 'index.ts')).href) as {
    reviewNarration: (args: { id: string; input: Record<string, unknown>; text: string }) => CheckerReport;
  };
  const pinned = JSON.parse(readFileSync(join(OUT, 'report.json'), 'utf8')) as {
    checker: { combinedSha256: string };
    cases: Array<{ samples: Array<{ seed: number; checker: { findings: Finding[]; decision: string } }> }>;
  };
  const pinnedBySeed = new Map<number, { findings: Finding[]; decision: string }>();
  for (const sample of pinned.cases[0]?.samples ?? []) {
    pinnedBySeed.set(sample.seed, sample.checker);
  }

  const rows = raw.map((row) => {
    const input = byCase.get(row.caseId)?.input;
    if (!input) throw new Error(`expected input missing for ${row.caseId}`);
    const report = checker.reviewNarration({ id: `${row.caseId}:s${row.seed}`, input, text: row.text });
    const factKinds = kinds(report.findings, 'fact');
    const styleKinds = kinds(report.findings, 'style');
    const reviewKinds = kinds(report.findings, 'review');
    const decision = !row.text.trim() || factKinds.length
      ? 'fail'
      : styleKinds.length
        ? 'style_fail'
        : reviewKinds.length ? 'pending' : 'pass';
    const old = pinnedBySeed.get(row.seed);
    const oldKinds = new Set(old?.findings.map((finding) => finding.kind) ?? []);
    const newKinds = new Set(report.findings.map((finding) => finding.kind));
    return {
      seed: row.seed,
      decision,
      pinnedDecision: old?.decision ?? null,
      factKinds,
      styleKinds,
      reviewKinds,
      mandatoryCovered: report.mandatory.filter((entry) => entry.expressed).length,
      mandatoryTotal: report.mandatory.length,
      newKindsVsPinned: [...newKinds].filter((kind) => !oldKinds.has(kind)).sort(),
      goneKindsVsPinned: [...oldKinds].filter((kind) => !newKinds.has(kind)).sort(),
      findings: report.findings.map((finding) => ({
        severity: finding.severity, kind: finding.kind, sentence: finding.sentence,
      })),
    };
  });

  const all = rows.flatMap((row) => row.findings);
  const diagnosis = {
    kind: 'lane12-n1-current-checker-diagnosis',
    createdAt: new Date().toISOString(),
    diagnosticOnly: true,
    doesNotReplacePinnedReport: true,
    modelRerun: false,
    nExpanded: false,
    source: {
      raw: join(OUT, 'raw.jsonl'),
      rawSha256: sha256(readFileSync(join(OUT, 'raw.jsonl'))),
      pinnedReport: join(OUT, 'report.json'),
      pinnedCheckerCombinedSha256: pinned.checker.combinedSha256,
      currentChecker: CHECKER_DIR,
      currentCheckerCombinedSha256: checkerHashes().combined,
      currentCheckerFiles: checkerHashes().files,
      currentCheckerSource: '01-input live worktree; not the pinned ec7ffc0e snapshot',
    },
    handoffChecks: {
      timeMissingStillFlagged: all.some((finding) => finding.kind === 'fact.time_missing'),
      personalityOmittedStillFlagged: all.some((finding) => finding.kind === 'fact.personality_omitted'),
      staleRemovedItemCaught: rows.find((row) => row.seed === 43)?.findings
        .some((finding) => finding.sentence.includes('锈穿')
          && /item|stale|removed|state/u.test(finding.kind)) ?? false,
      traitOwnerOrTraitCopyCaught: rows.find((row) => row.seed === 61)?.findings
        .some((finding) => finding.sentence.includes('讲究次序')
          && /owner|attribution|trait|personality_(mismatch|owner|copy)/u.test(finding.kind)) ?? false,
      firstPersonCaught: rows.find((row) => row.seed === 97)?.findings
        .some((finding) => finding.sentence.includes('我站在还书处')
          && /viewpoint|pronoun|first_person/u.test(finding.kind)) ?? false,
      statusRecitalStyleCaught: all.some((finding) => finding.severity === 'style'),
    },
    rows,
    note: 'Current-checker diagnosis only. The b01 result remains 0 fact-qualified under the pinned report; human review is still pending.',
  };

  mkdirSync(OUT, { recursive: true });
  writeFileSync(join(OUT, 'current-checker-diagnosis.json'), `${JSON.stringify(diagnosis, null, 2)}\n`, 'utf8');

  const lines: string[] = [];
  lines.push('# b01 six frozen texts: 01 current-checker diagnosis');
  lines.push('');
  lines.push(`- pinned checker: \`${pinned.checker.combinedSha256}\``);
  lines.push(`- current checker: \`${diagnosis.source.currentCheckerCombinedSha256}\``);
  lines.push('- model rerun: no; N expanded: no; diagnostic only, not a quality pass');
  lines.push('');
  lines.push('| seed | pinned | current | new kinds | gone kinds | coverage |');
  lines.push('|---|---|---|---|---|---|');
  for (const row of rows) {
    lines.push(`| ${row.seed} | ${row.pinnedDecision} | ${row.decision} | ${row.newKindsVsPinned.join(',') || '-'} | ${row.goneKindsVsPinned.join(',') || '-'} | ${row.mandatoryCovered}/${row.mandatoryTotal} |`);
  }
  lines.push('');
  lines.push('## Handoff checks');
  lines.push('');
  lines.push('```json');
  lines.push(JSON.stringify(diagnosis.handoffChecks, null, 2));
  lines.push('```');
  lines.push('');
  lines.push('No reference answer was read. This does not change the pinned b01 result or 01\'s standard.');
  lines.push('');
  writeFileSync(join(OUT, 'current-checker-diagnosis.md'), lines.join('\n'), 'utf8');
  console.log(JSON.stringify({ out: OUT, checker: diagnosis.source.currentCheckerCombinedSha256, checks: diagnosis.handoffChecks }, null, 2));
}

main().catch((error) => {
  console.error(error instanceof Error ? `${error.name}: ${error.message}` : String(error));
  process.exit(1);
});
