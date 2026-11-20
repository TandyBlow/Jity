// CPU-only contention tests for resource_lease.py. No model, no browser.
//
//   node scripts/product-acceptance/lease-contention.mjs
//
// Copies the real script into a temp directory (so the live lease is never
// touched) and exercises: simultaneous acquire, status-is-not-a-reservation,
// wrong-owner release, live-holder block, dead-holder takeover, owner release.
import { spawn, spawnSync } from 'node:child_process';
import { copyFileSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, '../../../..');
const leaseSource = resolve(repoRoot, '../resource_lease.py');
const root = mkdtempSync(join(tmpdir(), 'lease-test-'));
mkdirSync(join(root, 'resources'), { recursive: true });
copyFileSync(leaseSource, join(root, 'resource_lease.py'));

const checks = [];
function check(id, ok, detail) {
  checks.push({ id, ok, detail });
  console.log(`[${ok ? 'pass' : 'fail'}] ${id}${detail ? ` :: ${JSON.stringify(detail).slice(0, 240)}` : ''}`);
}
function run(args, cwd = root) {
  const result = spawnSync('python', ['-X', 'utf8', 'resource_lease.py', ...args], { cwd, encoding: 'utf8' });
  let parsed = null;
  try { parsed = JSON.parse(result.stdout.trim().split('\n').pop()); } catch { /* keep null */ }
  return { code: result.status, out: parsed, stdout: result.stdout, stderr: result.stderr };
}
function lockPath() { return join(root, 'resources', 'local-inference.lock'); }
function writeLock(record) { writeFileSync(lockPath(), JSON.stringify(record)); }
function readLock() {
  try { return JSON.parse(readFileSync(lockPath(), 'utf8')); } catch { return null; }
}
function clear() { try { rmSync(lockPath(), { force: true }); } catch { /* ignore */ } }

// 1. status says free, but a concurrent acquire is the reservation: second lane
//    must be busy even though it saw free a moment earlier.
clear();
const seen = run(['status']);
const holder = String(process.pid);
const a = run(['acquire', '--lane', 'lane-a', '--purpose', 'test', '--holder-pid', holder]);
const b = run(['acquire', '--lane', 'lane-b', '--purpose', 'test', '--holder-pid', holder]);
check('status-free-is-not-a-reservation', seen.out?.status === 'free' && a.out?.status === 'acquired' && b.out?.status === 'busy' && b.code === 2,
  { seen: seen.out?.status, a: a.out?.status, b: b.out?.status, bCode: b.code });
const tokenA = a.out?.token;
check('acquire-returns-owner-token', typeof tokenA === 'string' && tokenA.length >= 16, { tokenA: tokenA?.slice(0, 8) });

// 2. Wrong owner (same lane, wrong token) cannot release; the lock survives.
const wrong = run(['release', '--lane', 'lane-a', '--token', 'not-the-token']);
check('wrong-token-release-refused', wrong.out?.status === 'refused' && wrong.code === 3 && readLock()?.lane === 'lane-a', wrong.out);
// 3. Another lane cannot release either.
const wrongLane = run(['release', '--lane', 'lane-b', '--token', tokenA]);
check('other-lane-release-refused', wrongLane.out?.status === 'refused' && readLock()?.lane === 'lane-a', wrongLane.out);
// 4. Owner releases, then a second release is free (idempotent).
const own = run(['release', '--lane', 'lane-a', '--token', tokenA]);
const again = run(['release', '--lane', 'lane-a', '--token', tokenA]);
check('owner-release-then-free', own.out?.status === 'released' && again.out?.status === 'free', { own: own.out?.status, again: again.out?.status });

// 5. Live holder blocks takeover: write a record whose holderPid is a live
//    python child and whose age is very old.
clear();
const child = spawn('python', ['-c', 'import time; time.sleep(30)'], { stdio: 'ignore' });
await new Promise((done) => setTimeout(done, 400));
writeLock({ lane: 'live', purpose: 'test', acquiredAt: '2000-01-01T00:00:00+00:00', holderPid: child.pid, token: 'live-token' });
const blocked = run(['acquire', '--lane', 'lane-c', '--purpose', 'test', '--ttl-seconds', '1']);
check('live-holder-blocks-takeover', blocked.out?.status === 'busy' && readLock()?.lane === 'live', blocked.out);

// 6. Dead holder + expired TTL can be taken over atomically, with a reason.
clear();
writeLock({ lane: 'dead', purpose: 'test', acquiredAt: '2000-01-01T00:00:00+00:00', holderPid: 999999, token: 'dead-token' });
const takeover = run(['acquire', '--lane', 'lane-d', '--purpose', 'test', '--ttl-seconds', '1']);
check('dead-holder-takeover', takeover.out?.status === 'acquired' && /not alive|ttl/.test(takeover.out?.takeover ?? '') && readLock()?.lane === 'lane-d',
  { status: takeover.out?.status, takeover: takeover.out?.takeover });
child.kill();

// 7. A concurrent release of a stale-but-live lock by its own lane still works.
const tokenD = takeover.out?.token;
const deadRelease = run(['release', '--lane', 'lane-d', '--token', tokenD]);
check('takeover-owner-release', deadRelease.out?.status === 'released' && readLock() === null, deadRelease.out);

rmSync(root, { recursive: true, force: true });
const failed = checks.filter((entry) => !entry.ok);
console.log(`\n[done] ${failed.length ? 'FAIL' : 'PASS'} checks=${checks.length} failures=${failed.length}`);
process.exit(failed.length ? 1 : 0);
