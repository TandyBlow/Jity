// Build the G8 delivery manifest from the existing evidence. Reads, never
// re-runs. The world hashes are the registration the page enforces.

import { execFileSync } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';

const root = resolve(new URL('../../..', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'));
const git = (...args) => execFileSync('git', args, { cwd: root }).toString().trim();
const readJson = (path) => JSON.parse(readFileSync(resolve(root, path), 'utf8'));

const registration = readFileSync(resolve(root, 'frontend/src/lib/world-engine/local/static-world-registration.ts'), 'utf8');
const worldHash = (name) => {
  const match = new RegExp(`${name}:\\s*'([0-9a-f]{64})'`, 'u').exec(registration);
  if (!match) throw new Error(`registration has no ${name}`);
  return match[1];
};
const worldAsset = /STATIC_WORLD_ASSET\s*=\s*'([^']+)'/u.exec(registration)?.[1];
if (!worldAsset) throw new Error('registration has no asset');
const counts = /STATIC_WORLD_COUNTS\s*=\s*(\{[\s\S]*?\})/u.exec(registration)?.[1];
const worldCounts = counts ? JSON.parse(counts) : null;

const models = readJson('artifacts/goal/model-manifest.json');
const summary = readJson('artifacts/goal/acceptance/summary.json');

const manifest = {
  kind: 'jity-local-game-delivery',
  generatedAt: new Date().toISOString(),
  code: { gitHead: git('rev-parse', 'HEAD'), branch: git('rev-parse', '--abbrev-ref', 'HEAD') },
  world: {
    asset: worldAsset,
    stateDigest: worldHash('stateDigest'),
    fileSha256Lf: worldHash('fileSha256Lf'),
    initialDigest: worldHash('initialDigest'),
    counts: worldCounts,
  },
  models: models.models ?? models,
  acceptance: {
    summary: 'artifacts/goal/acceptance/summary.json',
    evidence: summary.sources,
    inputs: summary.gates.inputs,
    firstReadablePass: summary.gates.firstReadablePass,
    turnCapPass: summary.gates.turnCapPass,
    deadlineStops: summary.gates.deadlineStops,
    thresholds: summary.thresholds,
    failures: summary.gates.failures,
    note: 'D-019: the user abandoned the signature and the ten independent inputs; acceptance is technical evidence.',
  },
  reproduce: {
    install: 'cd frontend && npm ci',
    models: 'node frontend/scripts/fetch-models.mjs',
    build: 'cd frontend && npm run build',
    serve: 'cd frontend && npx next start -p 3177',
    accept: 'node frontend/scripts/product-acceptance/accept-world-local.mjs --base http://127.0.0.1:3177 --turns <chunk> --out <evidence> --fresh',
  },
};

const out = resolve(root, 'artifacts/local-game-delivery/manifest.json');
mkdirSync(dirname(out), { recursive: true });
writeFileSync(out, JSON.stringify(manifest, null, 2) + '\n');
console.log(`[manifest] ${out} inputs=${manifest.acceptance.inputs} head=${manifest.code.gitHead.slice(0, 8)}`);