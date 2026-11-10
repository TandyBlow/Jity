/** Focused settlement-lane verification. One worker only: the parallel-lane
 * convention forbids each lane from running a full frontend suite/build.
 * Usage: node scripts/parallel-settlement/run-focused.mjs
 */
import { spawnSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const frontend = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const vitest = resolve(frontend, 'node_modules/vitest/vitest.mjs');
const result = spawnSync(process.execPath, [
  vitest,
  'run',
  'src/lib/world-engine/local/semantics/settlement',
  'src/lib/world-engine/local/turn-execution',
  '--maxWorkers=1',
], { cwd: frontend, stdio: 'inherit' });

process.exit(result.status ?? 1);
