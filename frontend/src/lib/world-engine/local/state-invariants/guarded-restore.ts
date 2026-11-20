/** Restore path for a persisted local record: verify the recorded S0+delta
 * replay and active-chain bindings before the transport accepts the snapshot.
 * The raw `LocalWorldTransport.restore` predates this check and still trusts
 * its input; callers that restore from storage should use this function until
 * the guard is merged into the transport itself. */
import { LocalWorldTransport } from '../transport';
import { RecordInvariantError, verifySessionSnapshot, type InvariantReport } from './index';

export type GuardedRestoreOptions = Parameters<typeof LocalWorldTransport.restore>[1];

export async function verifyBeforeRestore(snapshot: unknown): Promise<InvariantReport> {
  const report = await verifySessionSnapshot(snapshot);
  if (!report.ok) throw new RecordInvariantError(report);
  return report;
}

export async function restoreVerified(
  snapshot: unknown,
  options: GuardedRestoreOptions = {},
): Promise<LocalWorldTransport> {
  await verifyBeforeRestore(snapshot);
  const transport = snapshot && typeof snapshot === 'object' && 'transport' in snapshot
    ? (snapshot as { transport: unknown }).transport
    : snapshot;
  return LocalWorldTransport.restore(transport as Parameters<typeof LocalWorldTransport.restore>[0], options);
}

/** Narrow helper for callers that already hold a transport record. */
export async function restoreRecordVerified(
  record: Parameters<typeof LocalWorldTransport.restore>[0],
  options: GuardedRestoreOptions = {},
): Promise<LocalWorldTransport> {
  await verifyBeforeRestore(record);
  return LocalWorldTransport.restore(record, options);
}
