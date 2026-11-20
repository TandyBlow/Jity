/** Explicit legacy migration for the localStorage-era save. The original text
 * is always preserved (a raw backup in the progress store and, unless asked
 * otherwise, the original localStorage key stays untouched). Corrupt input is
 * reported, backed up and never deleted or overwritten. */
import type { Id } from '../../types';
import type { LocalGameSnapshot } from '../session';
import { ProgressConflictError, type LocalProgressStore } from './types';

export const LEGACY_SNAPSHOT_KEY = 'jity.world.local.snapshot.v1';

export interface LegacyStorageLike {
  getItem(key: string): string | null;
  setItem?(key: string, value: string): void;
  removeItem?(key: string): void;
}

export interface LegacyMigrationOptions {
  storage?: LegacyStorageLike | null;
  sourceKey?: string;
  /** Only after an explicit user confirmation: remove the legacy key. */
  removeSource?: boolean;
  /** Also keep a sidecar copy inside localStorage (default true) in addition
   * to the raw backup held by the progress store. */
  localStorageBackup?: boolean;
  now?: number;
}

export interface LegacyMigrationResult {
  status: 'migrated' | 'absent' | 'corrupt' | 'already_saved' | 'save_failed' | 'unsupported';
  sourceKey: string;
  worldId?: Id;
  revision?: number;
  backupKey?: string;
  error?: string;
}

function defaultStorage(): LegacyStorageLike | null {
  try {
    if (typeof globalThis.localStorage !== 'undefined') return globalThis.localStorage as unknown as LegacyStorageLike;
  } catch { /* storage disabled */ }
  return null;
}

function isSnapshot(value: unknown): value is LocalGameSnapshot {
  const candidate = value as { transport?: { worldId?: unknown; state?: unknown; pointStates?: unknown; control?: unknown }; commands?: unknown };
  return !!candidate && typeof candidate === 'object' && !!candidate.transport && typeof candidate.transport.worldId === 'string'
    && !!candidate.transport.state && !!candidate.transport.pointStates && !!candidate.transport.control
    && Array.isArray(candidate.commands) && candidate.commands.every((item) => typeof item === 'string');
}

/** Migrates the old single-slot localStorage snapshot into the durable store.
 * Never destructive: the raw bytes are captured before anything is parsed. */
export async function migrateLegacySnapshot(store: LocalProgressStore, options: LegacyMigrationOptions = {}): Promise<LegacyMigrationResult> {
  const sourceKey = options.sourceKey ?? LEGACY_SNAPSHOT_KEY;
  const storage = options.storage ?? defaultStorage();
  if (!storage) return { status: 'unsupported', sourceKey };
  const raw = storage.getItem(sourceKey);
  if (raw == null) return { status: 'absent', sourceKey };
  const now = options.now ?? Date.now();
  const backupKey = `legacy:${sourceKey}:${now}`;
  await store.backupLegacy({ key: backupKey, sourceKey, raw, capturedAtEpochMilli: now });
  if (options.localStorageBackup !== false && storage.setItem) {
    try { storage.setItem(`${sourceKey}.backup.${now}`, raw); } catch { /* quota; the store backup still exists */ }
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch (error) {
    return { status: 'corrupt', sourceKey, backupKey, error: error instanceof Error ? error.message : String(error) };
  }
  if (!isSnapshot(parsed)) return { status: 'corrupt', sourceKey, backupKey, error: 'legacy_snapshot_shape_invalid' };
  const worldId = parsed.transport.worldId;
  try {
    const metadata = await store.save(worldId, parsed, { expectedRevision: 0, writerId: 'legacy-migration', now });
    if (options.removeSource && storage.removeItem) storage.removeItem(sourceKey);
    return { status: 'migrated', sourceKey, worldId, revision: metadata.revision, backupKey };
  } catch (error) {
    if (error instanceof ProgressConflictError) {
      return { status: 'already_saved', sourceKey, worldId, backupKey, revision: error.current?.revision };
    }
    return { status: 'save_failed', sourceKey, worldId, backupKey, error: error instanceof Error ? error.message : String(error) };
  }
}
