/** Read-only audit of 06's page wiring for progress sync.
 *
 * Before 09 spends a browser session on /world-local, the page must satisfy the
 * four required preconditions from 07's handoff. This reads 06's source (it
 * never writes it) and prints one line per precondition with the file:line that
 * satisfies or misses it, so 06 and 09 can see the same gate.
 *
 *   LANE06_ROOT=../../06-recovery ./node_modules/.bin/jiti \
 *     ./scripts/parallel-sync/page-wiring-audit.ts
 *
 * Exit code 1 when a required precondition is missing.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const lane06 = process.env.LANE06_ROOT
  ?? 'D:/others/Jity/.local/parallel-local-game/worktrees/06-recovery';
const pagePath = join(lane06, 'frontend/src/app/world-local/page.tsx');
const source = readFileSync(pagePath, 'utf8');
const lines = source.split(/\r?\n/u);

function find(predicate: (line: string) => boolean): number | null {
  const index = lines.findIndex(predicate);
  return index === -1 ? null : index + 1;
}

function callSite(name: string): { line: number; text: string } | null {
  // createProductSync<LocalGameSnapshot>({...}) and the plain form both count;
  // the import line ends with a comma, not a call.
  const line = find((entry) => {
    const index = entry.indexOf(name);
    if (index === -1) return false;
    const rest = entry.slice(index + name.length).trimStart();
    return rest.startsWith('(') || rest.startsWith('<');
  });
  if (line === null) return null;
  // Join the call until its closing paren so multi-line options are visible.
  const text = lines.slice(line - 1, line + 20).join('\n');
  return { line, text };
}

const syncCall = callSite('createProductSync');

interface Check {
  id: string;
  required: boolean;
  ok: boolean;
  where: string;
  fix: string;
}

const checks: Check[] = [
  {
    id: 'sync-call-exists',
    required: true,
    ok: Boolean(syncCall),
    where: syncCall ? `page.tsx:${syncCall.line}` : 'missing',
    fix: '01. call createProductSync for the world; nothing else uploads progress',
  },
  {
    id: 'storage-passed',
    // Informational since the adapter defaults to window.localStorage in a
    // browser; passing it explicitly is still clearer and survives future
    // storage changes (e.g. a test shim).
    required: false,
    ok: Boolean(syncCall && /storage\s*:/u.test(syncCall.text)),
    where: syncCall ? `page.tsx:${syncCall.line}` : 'missing',
    fix: '02 (info). storage: window.localStorage is now the browser default; pass it explicitly if the page swaps stores',
  },
  {
    id: 'restore-on-open',
    required: true,
    ok: /\b(?:sync\.)?restore\s*\(/u.test(source),
    where: find((line) => /\b(?:sync\.)?restore\s*\(/u.test(line))?.toString() ?? 'missing',
    fix: '03. open a local save when there is one; call restore() to pull the remote copy only when there is none',
  },
  {
    id: 'explicit-choice',
    required: true,
    ok: /\b(?:sync\.)?choose\s*\(/u.test(source),
    where: find((line) => /\b(?:sync\.)?choose\s*\(/u.test(line))?.toString() ?? 'missing',
    fix: '04. when flush() reports a conflict, show both copies and let the player choose(); never pick for them',
  },
  {
    id: 'avoid-text-from-transcript',
    // Informational: the product narration arm is 02's model, not 07's
    // composer, so this does not gate the page. The composer uses it whenever
    // it is the labelled fallback.
    required: false,
    ok: /avoidText/u.test(source),
    where: find((line) => /avoidText/u.test(line))?.toString() ?? 'missing',
    fix: '05 (info). when the 07 composer is the fallback, pass policy.avoidText from the session transcript',
  },
];

const report = {
  page: pagePath,
  at: new Date().toISOString(),
  ready: checks.every((check) => !check.required || check.ok),
  checks,
};
console.log(JSON.stringify(report, null, 2));
if (!report.ready) {
  console.error('NOT READY: the page wiring preconditions are not met');
  process.exit(1);
}
console.log('READY: the page wiring preconditions are met');
