/** Product adapters for the progress-sync client.
 *
 * 06 owns the local repository (`local/persistence`). This module only adapts
 * that repository and the browser's storage to the two small interfaces the
 * sync client needs, so wiring the product is a few lines and no duplicated
 * state:
 *
 *   const sync = createProductSync({ store, worldId, baseUrl, token });
 *   await sync.push(snapshot);          // the session already wrote the store
 *   await sync.restore();               // local save, else read the remote head
 *   await sync.flush();                 // after reconnect
 *
 * The product's session is the only writer of the durable store. Writing it a
 * second time from here is a real bug: 06's store checks a revision, so the
 * extra write moves the revision behind the session and the session's next save
 * fails as a conflict. `save()` therefore uploads only by default; set
 * `writeLocal: true` only for a caller that has no session writer.
 *
 * The snapshot stays the product's opaque `LocalGameSnapshot`; nothing here
 * reads or reinterprets world state, and no game fact is computed on a server.
 */

import { compareLineage, createWebStorageQueueStore, ProgressSyncClient, type StorageLike } from './client';
import type {
  HeadState,
  HeadStateStore,
  LocalSnapshotStore,
  ProgressConflictError,
  ResolveResult,
  SaveOutcome,
  SnapshotEnvelope,
} from './types';

/** The subset of 06's `LocalProgressStore` this adapter reads. Structural on
 * purpose: no cross-lane import and no second copy of the record shape. */
export interface ProductProgressStore<P = unknown> {
  load(worldId: string): Promise<{ snapshot: P } | null>;
  save(worldId: string, snapshot: P, options?: Record<string, unknown>): Promise<unknown>;
}

export function createLocalSnapshotStore<P>(store: ProductProgressStore<P>): LocalSnapshotStore<P> {
  return {
    async load(worldId: string): Promise<P | null> {
      const record = await store.load(worldId);
      return record ? record.snapshot : null;
    },
    async save(worldId: string, payload: P): Promise<void> {
      await store.save(worldId, payload);
    },
  };
}

/** Persist the last known remote head next to the save. Without it a reload
 * forgets which remote snapshot the local save descends from, and the first
 * save after reload would claim an empty world. */
export function createWebStorageHeadStore(
  storage: StorageLike,
  key = 'jity.progress-sync.heads.v1',
): HeadStateStore {
  const readAll = (): Record<string, HeadState> => {
    const raw = storage.getItem(key);
    if (!raw) return {};
    try {
      const parsed = JSON.parse(raw) as unknown;
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {};
      return parsed as Record<string, HeadState>;
    } catch {
      return {};
    }
  };
  return {
    async load(worldId: string): Promise<HeadState | null> {
      const stored = readAll()[worldId];
      if (!stored || typeof stored.revision !== 'number' || stored.headSnapshotId === undefined) return null;
      return stored;
    },
    async save(worldId: string, head: HeadState): Promise<void> {
      const all = readAll();
      all[worldId] = head;
      storage.setItem(key, JSON.stringify(all));
    },
  };
}

export interface ProductSyncOptions<P> {
  /** 06's local progress store (durable IndexedDB in the product). */
  store: ProductProgressStore<P>;
  worldId: string;
  /** Progress service origin; empty/absent means local-only play. */
  baseUrl?: string | null;
  token?: string | null;
  /** Browser storage for the offline queue and the last known head. */
  storage?: StorageLike | null;
  /** Write the durable store from this adapter too. False by default because
   * the product's session owns it and checks its revision; a second write
   * breaks the session's next save. */
  writeLocal?: boolean;
  fetchImpl?: typeof fetch;
  queueKey?: string;
  headKey?: string;
  timeoutMs?: number;
  retry?: { attempts?: number; baseDelayMs?: number; maxDelayMs?: number };
  sleep?: (milliseconds: number) => Promise<void>;
  now?: () => number;
  idFactory?: () => string;
}

export interface ProductSaveResult<P> {
  /** The local save always happens first; false only when it threw. */
  localSaved: boolean;
  outcome: SaveOutcome<P> | null;
  /** Present when the service is configured but this save was kept locally. */
  note?: string;
}

export interface ProductRestoreResult<P> {
  source: 'local' | 'remote' | 'none';
  snapshot: P | null;
  /** Unresolved conflict the player must decide; both copies stay stored. */
  conflict?: ProgressConflictError<P>;
  note?: string;
}

/** Whether the local save is behind, ahead of, or diverged from the remote. */
export type SyncRelation = 'local-only' | 'in-sync' | 'remote-ahead' | 'local-ahead' | 'diverged' | 'unknown';

export interface ProductSyncStatus {
  relation: SyncRelation;
  localRevision: number | null;
  /** Snapshot the local save descends from (last upload the page knows of). */
  baseSnapshotId: string | null;
  remote: { headSnapshotId: string | null; revision: number } | null;
  /** Filled when diverged: both leaves stay readable until the player chooses. */
  branches?: string[];
  note?: string;
}

export interface ProductFlushResult<P = unknown> {
  uploaded: number;
  conflicts: number;
  remaining: number;
  offline: boolean;
  /** The actual conflicts, so the page can show both copies and ask. */
  conflictList: Array<ProgressConflictError<P>>;
}

export interface ProductSync<P> {
  readonly client: ProgressSyncClient<P>;
  readonly worldId: string;
  /** Upload a snapshot after the session saved it (or, with `writeLocal`,
   * save it here first). Never throws for network problems. */
  save(snapshot: P, options?: { requestId?: string; localOnly?: boolean; localAlreadySaved?: boolean }): Promise<ProductSaveResult<P>>;
  /** Upload a snapshot the caller already saved locally (06's repository).
   * Keeps one durable record instead of writing it twice. */
  push(snapshot: P, options?: { requestId?: string }): Promise<ProductSaveResult<P>>;
  /** Local save if present, else the remote head. A conflict is returned, not merged. */
  restore(): Promise<ProductRestoreResult<P>>;
  /** Retry queued uploads. Safe to call on every reconnect and page load. */
  flush(): Promise<ProductFlushResult<P>>;
  /** Compare the local save with the remote head without writing anything. */
  status(): Promise<ProductSyncStatus>;
  /** The player's explicit choice after a visible conflict. */
  choose(choice: 'keep-remote' | 'keep-local-fork', conflict: ProgressConflictError<P>): Promise<ResolveResult<P>>;
  pending(): Promise<number>;
  /** Read one stored branch (both copies stay readable after a fork). */
  read(snapshotId: string): Promise<SnapshotEnvelope<P>>;
}

/** Build the sync surface the product page uses. With no baseUrl the returned
 * object still saves locally and reports `local-only`, so play never depends
 * on the service. */
export function createProductSync<P>(options: ProductSyncOptions<P>): ProductSync<P> {
  const { worldId } = options;
  const baseUrl = options.baseUrl?.trim() ? options.baseUrl.trim() : null;
  // A browser has localStorage and nothing else to lose: use it unless the
  // caller explicitly opted out with `storage: null`. 06's page forgot to pass
  // it, so the queue and the last known head vanished on reload and an offline
  // save could never be uploaded. Explicit `storage: null` still means "keep
  // everything in memory".
  const storage = options.storage === undefined
    ? (typeof globalThis.localStorage !== 'undefined' ? globalThis.localStorage : null)
    : options.storage;
  if (!storage && typeof globalThis.localStorage === 'undefined') {
    console.warn('[progress-sync] no browser storage: the offline queue and the last known head live in memory only.');
  }

  const client = new ProgressSyncClient<P>({
    baseUrl: baseUrl ?? 'http://unconfigured.invalid',
    token: options.token ?? undefined,
    fetchImpl: baseUrl ? options.fetchImpl : async () => {
      throw new TypeError('progress service is not configured');
    },
    localStore: createLocalSnapshotStore(options.store),
    headStore: storage ? createWebStorageHeadStore(storage, options.headKey) : undefined,
    queueStore: storage
      ? createWebStorageQueueStore(options.queueKey ?? 'jity.progress-sync.queue.v1', storage)
      : undefined,
    timeoutMs: options.timeoutMs,
    retry: options.retry,
    sleep: options.sleep,
    now: options.now,
    idFactory: options.idFactory,
  });

  return {
    client,
    worldId,
    async save(snapshot, saveOptions = {}) {
      // The session writes the durable store. Writing it here too moves the
      // stored revision behind the session and its next save fails as a
      // conflict, before any model call.
      const writeLocal = options.writeLocal === true && saveOptions.localAlreadySaved !== true;
      const localSaved = writeLocal ? await client.saveLocal(worldId, snapshot) : false;
      if (!baseUrl) {
        return { localSaved, outcome: null, note: 'progress service is not configured; nothing to upload' };
      }
      const outcome = await client.save(worldId, snapshot, {
        requestId: saveOptions.requestId,
        localOnly: saveOptions.localOnly,
        skipLocal: !writeLocal,
      });
      return { localSaved, outcome };
    },
    async push(snapshot, pushOptions = {}) {
      if (!baseUrl) {
        return { localSaved: false, outcome: null, note: 'progress service is not configured; nothing to upload' };
      }
      const outcome = await client.save(worldId, snapshot, {
        requestId: pushOptions.requestId,
        skipLocal: true,
      });
      return { localSaved: false, outcome };
    },
    async restore() {
      const local = await client.loadLocal(worldId);
      if (!baseUrl) {
        return {
          source: local ? 'local' : 'none',
          snapshot: local,
          note: local ? undefined : 'no local save and no progress service configured',
        };
      }
      if (local) {
        // Local is the faster path; the queue/head explain divergence later.
        return { source: 'local', snapshot: local };
      }
      try {
        const pulled = await client.pullLatest(worldId, { saveLocal: options.writeLocal === true });
        return {
          source: pulled.snapshot ? 'remote' : 'none',
          snapshot: pulled.snapshot ? pulled.snapshot.payload : null,
        };
      } catch (error) {
        return {
          source: 'none',
          snapshot: null,
          note: error instanceof Error ? error.message : String(error),
        };
      }
    },
    async flush() {
      if (!baseUrl) {
        return { uploaded: 0, conflicts: 0, remaining: 0, offline: false, conflictList: [] };
      }
      const result = await client.flush();
      return {
        uploaded: result.uploaded.length,
        conflicts: result.conflicts.length,
        remaining: result.remaining,
        offline: result.offline,
        conflictList: result.conflicts.map((entry) => entry.conflict),
      };
    },
    async status() {
      const local = await client.loadLocal(worldId);
      const base = (await client.lastKnownHead(worldId))?.headSnapshotId ?? null;
      if (!baseUrl) {
        return {
          relation: local ? 'local-only' : 'unknown',
          localRevision: null,
          baseSnapshotId: base,
          remote: null,
          note: 'progress service is not configured',
        };
      }
      let head;
      try {
        head = await client.peekHead(worldId);
      } catch (error) {
        return {
          relation: local ? 'local-only' : 'unknown',
          localRevision: null,
          baseSnapshotId: base,
          remote: null,
          note: error instanceof Error ? error.message : String(error),
        };
      }
      const remote = { headSnapshotId: head.headSnapshotId, revision: head.revision };
      if (!local) return { relation: remote.headSnapshotId ? 'remote-ahead' : 'unknown', localRevision: null, baseSnapshotId: base, remote };
      if (!base) {
        if (!remote.headSnapshotId) {
          return { relation: 'local-ahead', localRevision: null, baseSnapshotId: null, remote };
        }
        try {
          const graph = await client.peekGraph(worldId);
          return {
            relation: 'diverged',
            localRevision: null,
            baseSnapshotId: null,
            remote,
            branches: graph.branches,
            note: 'the local save has no recorded remote base; both copies stay stored',
          };
        } catch {
          return { relation: 'diverged', localRevision: null, baseSnapshotId: null, remote };
        }
      }
      if (remote.headSnapshotId === base) return { relation: 'in-sync', localRevision: null, baseSnapshotId: base, remote };
      try {
        const graph = await client.peekGraph(worldId);
        if (!remote.headSnapshotId) {
          return { relation: 'local-ahead', localRevision: null, baseSnapshotId: base, remote, branches: graph.branches };
        }
        const comparison = compareLineage(base, remote.headSnapshotId, graph.nodes);
        if (comparison.leftIsAncestorOfRight) {
          return { relation: 'remote-ahead', localRevision: null, baseSnapshotId: base, remote, branches: graph.branches };
        }
        if (comparison.rightIsAncestorOfLeft) {
          return { relation: 'local-ahead', localRevision: null, baseSnapshotId: base, remote, branches: graph.branches };
        }
        return { relation: 'diverged', localRevision: null, baseSnapshotId: base, remote, branches: graph.branches };
      } catch (error) {
        // The base may be a snapshot this device never uploaded (e.g. storage
        // cleared elsewhere); the relation is genuinely unknown, not a guess.
        return {
          relation: 'unknown',
          localRevision: null,
          baseSnapshotId: base,
          remote,
          note: error instanceof Error ? error.message : String(error),
        };
      }
    },
    choose(choice, conflict) {
      return client.resolveConflict(conflict, choice, { saveLocal: options.writeLocal === true });
    },
    pending() {
      return client.pending();
    },
    read(snapshotId) {
      return client.read(worldId, snapshotId);
    },
  };
}
