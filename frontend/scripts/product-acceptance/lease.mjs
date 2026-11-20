// Mandatory local-inference lease for 09 entrypoints.
//
// The real inference entrypoint must reserve the GPU before any model load and
// release only after its browser/engines are gone. `status` is not a
// reservation; this helper performs the atomic acquire and throws if another
// live holder owns the lease. The holder pid is the driver process, not the
// short-lived python CLI, so the lock does not look dead on return.
import { spawnSync } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const leaseScript = resolve(here, '../../../../../resource_lease.py');

export function acquireLease({ lane = '09-ui', purpose = 'local inference', ttlSeconds = 1800 } = {}) {
  const token = randomBytes(16).toString('hex');
  const result = spawnSync(
    'python',
    ['-X', 'utf8', leaseScript, 'acquire', '--lane', lane, '--purpose', purpose, '--token', token,
      '--holder-pid', String(process.pid), '--ttl-seconds', String(ttlSeconds)],
    { encoding: 'utf8' },
  );
  const line = (result.stdout ?? '').trim().split('\n').pop() ?? '';
  let parsed = null;
  try { parsed = JSON.parse(line); } catch { /* keep null */ }
  if (result.status !== 0 || parsed?.status !== 'acquired') {
    const holder = parsed?.holder ? JSON.stringify(parsed.holder).slice(0, 400) : (result.stderr || line).slice(0, 400);
    const error = new Error(`inference lease unavailable: ${holder}`);
    error.holder = parsed?.holder ?? null;
    throw error;
  }
  let released = false;
  const release = () => {
    if (released) return { status: 'free' };
    released = true;
    const out = spawnSync('python', ['-X', 'utf8', leaseScript, 'release', '--lane', lane, '--token', token], { encoding: 'utf8' });
    return out.stdout?.trim() ?? '';
  };
  // A killed driver would otherwise leave a lock that only the dead-pid
  // takeover can clear. Release on normal termination signals too; the token
  // check still stops this process from freeing someone else's lock.
  const onSignal = (signal) => { release(); process.exit(signal === 'SIGINT' ? 130 : 143); };
  process.once('SIGINT', onSignal);
  process.once('SIGTERM', onSignal);
  process.once('exit', release);
  return { token, record: parsed, release };
}
