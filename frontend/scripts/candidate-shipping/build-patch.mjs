// Generate the minimal wiring patch for the narration candidate selection.
//
// The main integration tree is a different worktree with live, uncommitted
// edits. This script therefore reads THOSE bytes, records their sha256, and
// emits a patch that applies to exactly that snapshot:
//
//   node scripts/candidate-shipping/build-patch.mjs [--tree <integration tree>]
//
// Output (never overwritten, content-addressed):
//   patches/world-narration-candidate-<input8>-<patch8>.patch
//   patches/manifest.json
//
// The patch edits only `game-model.ts` and adds the selection module; the page
// needs no change. Prerequisites: lane 02's beats commit (211fd463 / 92c2d95e)
// and lane 04's constrained candidate (05aa9562) must be in the target tree,
// because the adapters import their modules.
import { createHash } from 'node:crypto';
import { execFileSync, spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, statSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const frontend = resolve(here, '../..');
const repo = resolve(frontend, '..');
const flag = (name, fallback) => {
  const index = process.argv.indexOf(name);
  return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
};
const target = resolve(flag('--tree', process.env.MAIN_TREE ?? 'D:/others/Jity/.local/world-narration-worktree'));
const source = resolve(flag('--source', repo));
const outDir = resolve(here, 'patches');
const sha256 = (bytes) => createHash('sha256').update(bytes).digest('hex');

const GAME_MODEL = 'frontend/src/lib/world-engine/local/game-model.ts';
const SELECTION_DIR = 'frontend/src/lib/world-engine/local/narration-candidates/selection';

/** Exact-text insertions. Each anchor must occur exactly once in the live
 * file; a missing/ambiguous anchor stops the build instead of guessing. */
const TRANSFORMS = [
  {
    id: 'import-selection',
    anchor: "import { createActionHandlers, type HandlerResult } from './semantics/actions';\n",
    insert: "import { createNarrationRunner } from './narration-candidates/selection';\n",
  },
  {
    id: 'option-narration-candidate',
    anchor: "  narrationMode?: 'legacy' | 'instruct';\n",
    insert: [
      '  /** Internal narration candidate selection. `auto` only offers candidates',
      '   * whose real-model evidence is positive, so the shipped default changes',
      '   * nothing until one is accepted; `trained` enables the committed-fact',
      '   * beats candidate for evaluation runs. Never a player-visible option. */',
      "  narrationCandidate?: 'auto' | 'trained' | 'instruct' | 'constrained' | 'builtin';",
      '',
    ].join('\n'),
  },
  {
    id: 'field-narration-runner',
    anchor: '  private recentEvents: string[] = [];\n',
    insert: [
      '  private lastAcceptedNarration: string | null = null;',
      '  private readonly narrationRunner: ReturnType<typeof createNarrationRunner> | null;',
      '',
    ].join('\n'),
  },
  {
    id: 'constructor-runner',
    anchor: '    this.options = options;\n',
    insert: [
      '    // Internal selection only: with no product-default candidate,',
      '    // `generate()` returns `fallback` before a single candidate call, so',
      '    // enabling this option cannot add model work to a normal turn.',
      "    this.narrationRunner = (options.narrationCandidate ?? 'auto') === 'builtin'",
      '      ? null',
      '      : createNarrationRunner({',
      '        engine: this.narrationEngine,',
      "        candidate: options.narrationCandidate ?? 'auto',",
      '        temperature: options.narrationTemperature,',
      '        maxTokens: options.narrationMaxTokens,',
      '        timeoutMs: options.narrationTimeoutMs,',
      '      });',
      '',
    ].join('\n'),
  },
  {
    id: 'narration-candidate-first',
    anchor: '    const view = after.protagonistId;\n',
    insert: [
      '    if (this.narrationRunner) {',
      '      const adopted = await this.adoptNarrationCandidate(pointId, data.before ?? null, data.delta ?? {}, after);',
      '      if (adopted) return adopted;',
      '    }',
      '',
    ].join('\n'),
  },
  {
    id: 'narration-candidate-method',
    anchor: '    return { value: text as unknown as Json, raw: text, ms: performance.now() - started, fallback: !accepted, error: reason };\n  }\n',
    insert: [
      '',
      "  /** Candidate path. Only a verified scene (`kind: 'adopted'`) becomes this",
      "   * point's narration; every other outcome logs an internal reason and returns",
      '   * null, so the in-model writer below keeps producing the honestly-labelled',
      '   * fallback text the page already shows today. */',
      '  private async adoptNarrationCandidate(',
      '    pointId: Id,',
      '    before: WorldState | null,',
      '    delta: { timeAdvance?: TimeAdvance | null; entityDeltas?: Record<Id, EntityDelta> },',
      '    after: WorldState,',
      '  ): Promise<Generated | null> {',
      '    if (!this.narrationRunner) return null;',
      '    const result = await this.narrationRunner.generate({',
      '      pointId,',
      '      before,',
      '      delta,',
      '      after,',
      '      playerInput: this.lastPlayerInput,',
      '      settledResults: this.lastResultsText ? [this.lastResultsText] : [],',
      '      priorText: this.lastAcceptedNarration,',
      '      recentEvents: this.recentEvents,',
      '    }, (state) => this.options.onNarrationProgress?.({ pointId, raw: state.text, elapsedMs: state.elapsedMs }));',
      "    if (result.kind !== 'adopted') {",
      "      console.info('[narration] candidate fallback', result.reason);",
      '      return null;',
      '    }',
      '    this.lastAcceptedNarration = result.text;',
      "    this.options.onTask?.('narration', pointId, {",
      '      ms: result.timings.totalMs,',
      "      fallback: result.grade === 'program',",
      "      ...(result.grade === 'program' ? { error: '程序按已结算事实成文' } : {}),",
      '      raw: result.text,',
      '      promptChars: result.promptChars,',
      '    });',
      '    this.options.onNarrationComplete?.({ pointId, raw: result.text, completion: result.completion });',
      '    return { value: result.text as unknown as Json, raw: result.text, ms: result.timings.totalMs, fallback: false };',
      '  }',
      '',
    ].join('\n'),
  },
];

function mustReplace(text, transform) {
  const count = text.split(transform.anchor).length - 1;
  if (count !== 1) {
    throw new Error(`transform ${transform.id}: anchor occurs ${count} times (expected 1) in the live file`);
  }
  const at = text.indexOf(transform.anchor) + transform.anchor.length;
  return text.slice(0, at) + transform.insert + text.slice(at);
}

function readTarget(relativePath) {
  const absolute = join(target, relativePath);
  if (!existsSync(absolute)) throw new Error(`missing live input: ${absolute}`);
  return { absolute, bytes: readFileSync(absolute) };
}

/** Minimal unified diff via git, with repo-relative headers. */
function unifiedDiff(relativePath, oldText, newText) {
  if (oldText === newText) return '';
  const scratch = mkdtempSync(join(tmpdir(), 'shipping-diff-'));
  try {
    const oldFile = join(scratch, 'old', relativePath);
    const newFile = join(scratch, 'new', relativePath);
    mkdirSync(dirname(oldFile), { recursive: true });
    mkdirSync(dirname(newFile), { recursive: true });
    writeFileSync(oldFile, oldText);
    writeFileSync(newFile, newText);
    // `git diff --no-index` exits 1 when the files differ: that is the
    // expected path, so the status is checked as 0 or 1 and stdout is used.
    const diff = spawnSync('git', ['diff', '--no-index', '--no-color', '--', `old/${relativePath}`, `new/${relativePath}`], {
      cwd: scratch, encoding: 'utf8', maxBuffer: 32 * 1024 * 1024,
    });
    if (diff.status !== 0 && diff.status !== 1) throw new Error(`git diff failed: ${diff.stderr}`);
    return diff.stdout.replaceAll('a/old/', 'a/').replaceAll('b/new/', 'b/');
  } finally {
    rmSync(scratch, { recursive: true, force: true });
  }
}

/** New-file diff: no old bytes, so emit the standard form by hand. */
function addedDiff(relativePath, text) {
  const lines = text.endsWith('\n') ? text.slice(0, -1).split('\n') : text.split('\n');
  const body = lines.map((line) => `+${line}`).join('\n');
  return [
    `diff --git a/${relativePath} b/${relativePath}`,
    'new file mode 100644',
    '--- /dev/null',
    `+++ b/${relativePath}`,
    `@@ -0,0 +1,${lines.length} @@`,
    body,
    '',
  ].join('\n');
}

function collectAdditions() {
  const root = join(source, SELECTION_DIR);
  if (!existsSync(root)) throw new Error(`selection module missing in source tree: ${root}`);
  // Runtime files only: a lane-owned test file stays in the lane and is not
  // shipped into the product tree.
  const files = readdirSync(root).filter((name) => name.endsWith('.ts') && !name.endsWith('.test.ts')).sort();
  return files.map((name) => {
    const relativePath = `${SELECTION_DIR}/${name}`;
    const bytes = readFileSync(join(root, name));
    return { relativePath, bytes, sha256: sha256(bytes) };
  });
}

function verifyApply(patchText, inputText) {
  const scratch = mkdtempSync(join(tmpdir(), 'shipping-apply-'));
  try {
    const file = join(scratch, GAME_MODEL);
    mkdirSync(dirname(file), { recursive: true });
    writeFileSync(file, inputText);
    writeFileSync(join(scratch, 'candidate.patch'), patchText);
    execFileSync('git', ['apply', '--check', '-p1', 'candidate.patch'], { cwd: scratch, stdio: 'pipe' });
    return { ok: true, command: 'git apply --check -p1 candidate.patch' };
  } catch (error) {
    return { ok: false, command: 'git apply --check -p1 candidate.patch', error: String(error.stderr ?? error.message).trim() };
  } finally {
    rmSync(scratch, { recursive: true, force: true });
  }
}

/** Line endings of the integration file: transforms are written against LF,
 * and the patched text is restored to the file's own ending so the diff applies
 * to the exact bytes that were hashed. */
const LF = String.fromCharCode(10);
const CRLF = String.fromCharCode(13, 10);
const live = readTarget(GAME_MODEL);
const sourceText = live.bytes.toString('utf8');
const eol = sourceText.includes(CRLF) ? CRLF : LF;
let patched = sourceText.split(CRLF).join(LF);
for (const transform of TRANSFORMS) patched = mustReplace(patched, transform);
if (eol === CRLF) patched = patched.split(LF).join(CRLF);

const additions = collectAdditions();
const header = [
  '# Narration candidate selection wiring (lane 06 shipping).',
  '#',
  '# Inputs (sha256) — regenerate when the live files change:',
  `#   ${GAME_MODEL}  ${sha256(live.bytes)}`,
  '# Prerequisites: lane 02 beats commits 211fd463 / 92c2d95e and lane 04',
  '# constrained candidate 05aa9562. New module files are additions from lane 06.',
  '#',
  '# Default `auto` selects the constrained program candidate (C): fact-grounded,',
  '# instant, and labelled by the page as a downgrade. To evaluate the committed-',
  '# fact beats candidate (B) on an instruct narration model, pass',
  "#   narrationCandidate: 'trained'",
  '# in the LocalGameModel options (page.tsx). The page file itself does not change.',
  '',
].join('\n');
const patchText = [
  header,
  ...additions.flatMap((addition) => [addedDiff(addition.relativePath, addition.bytes.toString('utf8')).trimEnd(), '']),
  unifiedDiff(GAME_MODEL, sourceText, patched).trimEnd(),
  '',
].join('\n');

const inputHash = sha256(live.bytes).slice(0, 12);
const patchHash = sha256(patchText).slice(0, 12);
const check = verifyApply(patchText, sourceText);
mkdirSync(outDir, { recursive: true });
const patchFile = `world-narration-candidate-${inputHash}-${patchHash}.patch`;
const patchPath = join(outDir, patchFile);
if (existsSync(patchPath) && sha256(readFileSync(patchPath)) !== sha256(patchText)) {
  throw new Error(`refusing to overwrite ${patchFile} with different bytes`);
}
writeFileSync(patchPath, patchText);

const manifestPath = join(outDir, 'manifest.json');
const previous = existsSync(manifestPath) ? JSON.parse(readFileSync(manifestPath, 'utf8')) : { patches: [] };
const entry = {
  patch: `patches/${patchFile}`,
  patchSha256: sha256(patchText),
  patchBytes: statSync(patchPath).size,
  generatedAt: new Date().toISOString(),
  target,
  inputs: [{ path: GAME_MODEL, sha256: sha256(live.bytes) }],
  transforms: TRANSFORMS.map((transform) => transform.id),
  additions: additions.map((addition) => ({ path: addition.relativePath, sha256: addition.sha256 })),
  edits: [GAME_MODEL],
  pageChanges: [],
  prerequisites: [
    'lane 02 commits 211fd463 + 92c2d95e (narration-generation beats, short-scene acceptance) must be present',
    'lane 04 commit 05aa9562 (constrained candidate, facts-only scene hints) must be present',
    'no page.tsx change: selection stays internal and the page keeps its callbacks',
  ],
  applyCheck: check,
};
const patches = previous.patches.filter((item) => item.patch !== entry.patch);
patches.push(entry);
for (const item of patches) {
  // Same input snapshot, different patch bytes -> the newer one supersedes it,
  // but the old file stays on disk for review (nothing is overwritten).
  item.superseded = item.patch !== entry.patch
    && item.inputs.every((input) => entry.inputs.some((current) => current.path === input.path && current.sha256 === input.sha256))
    && item.patchSha256 !== entry.patchSha256;
  item.stale = item.inputs.some((input) => {
    const current = join(item.target, input.path);
    return !existsSync(current) || sha256(readFileSync(current)) !== input.sha256;
  });
}
// `--prune` retires superseded patch files from the shipped directory but
// keeps their identity (name + sha256 + inputs) in `history`; old bytes are
// never silently replaced.
let history = previous.history ?? [];
if (process.argv.includes('--prune')) {
  const keep = patches.filter((item) => item.patch === entry.patch);
  const removed = patches.filter((item) => item.patch !== entry.patch);
  for (const item of removed) {
    const absolute = join(here, item.patch);
    if (existsSync(absolute)) rmSync(absolute);
  }
  history = [...history, ...removed
    .filter((item) => !history.some((old) => old.patchSha256 === item.patchSha256))
    .map((item) => ({
      patch: item.patch,
      patchSha256: item.patchSha256,
      input: item.inputs,
      retiredAt: new Date().toISOString(),
      reason: item.stale ? 'stale_input' : 'superseded',
    }))];
  patches.splice(0, patches.length, ...keep);
}
writeFileSync(manifestPath, JSON.stringify({ updatedAt: new Date().toISOString(), patches, history }, null, 2) + String.fromCharCode(10));
console.log(JSON.stringify({
  patch: `patches/${patchFile}`, bytes: entry.patchBytes,
  input: entry.inputs, additions: additions.length, applyCheck: check,
  staleEntries: patches.filter((item) => item.stale).length,
}, null, 2));
