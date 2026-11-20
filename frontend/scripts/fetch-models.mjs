// External model fetch for the browser-local product (D-010).
// Downloads the exact GGUF files the page serves, verifies bytes + sha256, and
// records the manifest in artifacts/goal/. Weights stay out of git.
//
//   node frontend/scripts/fetch-models.mjs
//
// Exit 0 only when every file matches its pinned hash.

import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { createReadStream, existsSync, mkdirSync, renameSync, statSync, unlinkSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../..');
const modelsDir = join(root, 'frontend', 'public', 'models');
const manifestPath = join(root, 'artifacts', 'goal', 'model-manifest.json');

const MODELS = [
  {
    role: 'semantic',
    file: 'Qwen3-0.6B-Q4_K_M.gguf',
    url: 'https://huggingface.co/unsloth/Qwen3-0.6B-GGUF/resolve/main/Qwen3-0.6B-Q4_K_M.gguf',
    repo: 'unsloth/Qwen3-0.6B-GGUF',
    repoRevision: '50968a4468ef4233ed78cd7c3de230dd1d61a56b',
    bytes: 396_705_472,
    sha256: 'ac2d97712095a558e31573f62f466a3f9d93990898b0ec79d7c974c1780d524a',
    license: 'Apache-2.0',
  },
  {
    role: 'narration',
    file: 'Qwen3-1.7B-Q4_K_M.gguf',
    url: 'https://huggingface.co/unsloth/Qwen3-1.7B-GGUF/resolve/main/Qwen3-1.7B-Q4_K_M.gguf',
    repo: 'unsloth/Qwen3-1.7B-GGUF',
    repoRevision: 'd7f544eead698dbd1f15126ef60b45a1e1933222',
    bytes: 1_107_409_472,
    sha256: 'b139949c5bd74937ad8ed8c8cf3d9ffb1e99c866c823204dc42c0d91fa181897',
    license: 'Apache-2.0',
  },
];

function hashFile(path) {
  return new Promise((done, fail) => {
    const hash = createHash('sha256');
    createReadStream(path)
      .on('data', (chunk) => hash.update(chunk))
      .on('error', fail)
      .on('end', () => done(hash.digest('hex')));
  });
}

async function download(model) {
  const target = join(modelsDir, model.file);
  const part = `${target}.part`;
  // curl (not fetch): it honors the machine proxy env; undici in Node 22 does not.
  const result = spawnSync('curl', [
    '--fail', '--location', '--retry', '3', '--retry-delay', '2',
    '--progress-bar', '--output', part, model.url,
  ], { stdio: ['ignore', 'inherit', 'inherit'] });
  if (result.status !== 0) {
    try { unlinkSync(part); } catch { /* no part */ }
    throw new Error(`${model.file}: curl exited ${result.status}`);
  }
  const bytes = statSync(part).size;
  const digest = await hashFile(part);
  if (bytes !== model.bytes || digest !== model.sha256) {
    unlinkSync(part);
    throw new Error(`${model.file}: got ${bytes} bytes / ${digest}, expected ${model.bytes} / ${model.sha256}`);
  }
  renameSync(part, target);
}

async function verify(model, target) {
  if (!existsSync(target)) return null;
  const bytes = statSync(target).size;
  if (bytes !== model.bytes) return { bytes, sha256: null };
  return { bytes, sha256: await hashFile(target) };
}

const results = [];
mkdirSync(modelsDir, { recursive: true });
for (const model of MODELS) {
  const target = join(modelsDir, model.file);
  const check = await verify(model, target);
  if (check && check.sha256 === model.sha256) {
    console.log(`[ok] ${model.file} already verified (${model.bytes} bytes)`);
  } else {
    if (check) console.log(`[stale] ${model.file}: ${check.bytes} bytes / ${check.sha256 ?? 'size mismatch'}; refetching`);
    await download(model);
    console.log(`[ok] ${model.file} downloaded and verified`);
  }
  results.push({
    role: model.role, file: model.file, path: `frontend/public/models/${model.file}`,
    url: model.url, repo: model.repo, repoRevision: model.repoRevision,
    bytes: model.bytes, sha256: model.sha256, license: model.license,
    verifiedAt: new Date().toISOString(),
  });
}

mkdirSync(dirname(manifestPath), { recursive: true });
writeFileSync(manifestPath, JSON.stringify({
  kind: 'jity-model-manifest',
  generatedAt: new Date().toISOString(),
  note: 'Weights are gitignored; this manifest is the contract. Fetch with node frontend/scripts/fetch-models.mjs.',
  tokenizer: 'Embedded in each GGUF (wllama reads it from the file); no separate tokenizer asset is served.',
  models: results,
}, null, 2));
console.log(`[manifest] ${manifestPath}`);
