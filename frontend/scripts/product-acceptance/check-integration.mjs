// Validates the integrator's published product record before 09 spends a GPU
// lease. This is a cheap, read-only gate: it never starts a server and never
// trusts prose in place of the fields the acceptance driver consumes.
//
//   node scripts/product-acceptance/check-integration.mjs [--json]
//
// Exit codes: 0 all required fields present; 2 missing/invalid.

import { existsSync, readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../../../../..');
const path = resolve(root, 'results/product/integration.json');
const asJson = process.argv.includes('--json');

const REQUIRED = [
  ['product.worktree', (d) => d?.product?.worktree ?? d?.worktree],
  ['product.branch', (d) => d?.product?.branch ?? d?.branch],
  ['product.head', (d) => d?.product?.head ?? d?.head],
  ['product.url', (d) => d?.product?.url ?? d?.url],
  ['startup.command', (d) => d?.startup?.command ?? d?.product?.startup?.command],
  ['startup.port', (d) => d?.startup?.port ?? d?.product?.port],
  ['models (name + served path + sha256 + bytes)', (d) => {
    const models = d?.models ?? d?.assets?.models ?? d?.model;
    if (!models) return null;
    const list = Array.isArray(models) ? models : Object.values(models);
    const good = list.filter((model) => model && (model.path || model.servedPath || model.file)
      && model.sha256 && Number(model.bytes) > 0);
    return good.length === list.length && list.length > 0 ? good : null;
  }],
  ['crossOriginIsolation (true/false as measured by the integrator)', (d) => {
    const value = d?.product?.crossOriginIsolated ?? d?.crossOriginIsolated;
    return typeof value === 'boolean' ? value : null;
  }],
  ['localStorage key(s) or progress store description', (d) => d?.persistence?.localStorageKeys ?? d?.persistence?.store ?? d?.storage],
];

const problems = [];
let record = null;
if (!existsSync(path)) {
  problems.push(`missing file: ${path}`);
} else {
  try {
    record = JSON.parse(readFileSync(path, 'utf8'));
  } catch (error) {
    problems.push(`unreadable JSON: ${String(error).slice(0, 200)}`);
  }
}
if (record) {
  for (const [label, read] of REQUIRED) {
    let value = null;
    try { value = read(record); } catch { value = null; }
    if (value === null || value === undefined || value === '' || value === false && label.startsWith('crossOrigin')) {
      if (label.startsWith('crossOrigin') && value === false) {
        problems.push(`${label}: published as false — the product page is not cross-origin isolated; acceptance will record this as a product failure`);
      } else {
        problems.push(`missing: ${label}`);
      }
    }
  }
}

const result = {
  at: new Date().toISOString(),
  path,
  ok: problems.length === 0,
  problems,
  product: record ? {
    worktree: record?.product?.worktree ?? record?.worktree ?? null,
    branch: record?.product?.branch ?? record?.branch ?? null,
    head: record?.product?.head ?? record?.head ?? null,
    url: record?.product?.url ?? record?.url ?? null,
  } : null,
};
if (asJson) console.log(JSON.stringify(result, null, 2));
else {
  console.log(`[integration] ${result.ok ? 'ok' : 'incomplete'} ${path}`);
  for (const problem of problems) console.log(`  - ${problem}`);
}
process.exit(result.ok ? 0 : 2);
