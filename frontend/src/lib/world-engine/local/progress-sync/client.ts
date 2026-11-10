/** Browser sync client for saved progress.
 *
 * Contract:
 * - local save happens first and is never blocked by the server;
 * - every remote write carries expectedHead + expectedRevision;
 * - every write has a requestId, so retries are idempotent;
 * - 409 is returned to the caller as an explicit conflict, never auto-merged;
 * - offline uploads stay in a queue and can be flushed later;
 * - choosing a branch only moves the head; both branches remain readable.
 *
 * The server never sees WorldState semantics, only this opaque snapshot.
 */

import { MemoryQueueStore } from './queue';
import type {
  ConflictChoice,
  FlushConflict,
  FlushOutcome,
  GraphState,
  HeadState,
  HeadStateStore,
  LocalSnapshotStore,
  OfflineQueueStore,
  ProgressConflictError as ProgressConflictErrorType,
  PullResult,
  QueuedUpload,
  ResolveResult,
  SaveOutcome,
  SelectHeadRequest,
  SelectHeadResult,
  SnapshotEnvelope,
  SnapshotId,
  UploadRequest,
  UploadResult,
  WorldId,
} from './types';
import { ProgressConflictError, ProgressSyncError } from './types';

export { compareLineage, lineageNodes, type LineageComparison, type LineageNode } from './lineage';
export { MemoryQueueStore, createWebStorageQueueStore, type StorageLike } from './queue';
export * from './types';

export interface RetryOptions {
  attempts?: number;
  baseDelayMs?: number;
  maxDelayMs?: number;
}

export interface ProgressSyncClientOptions<P = unknown> {
  /** Service origin, e.g. http://127.0.0.1:8010 (or .../local-progress). */
  baseUrl: string;
  fetchImpl?: typeof fetch;
  token?: string;
  timeoutMs?: number;
  localStore?: LocalSnapshotStore<P>;
  /** Persist the last known remote head so a reload can still save correctly. */
  headStore?: HeadStateStore;
  queueStore?: OfflineQueueStore;
  retry?: RetryOptions;
  sleep?: (milliseconds: number) => Promise<void>;
  now?: () => number;
  idFactory?: () => string;
}

export interface SaveOptions {
  expectedHead?: SnapshotId | null;
  expectedRevision?: number;
  parentSnapshotIds?: SnapshotId[];
  activate?: boolean;
  requestId?: string;
  /** Save only on the local store; useful while deliberately playing offline. */
  localOnly?: boolean;
  /** The caller already wrote its own durable record (06's repository does),
   * so do not write it a second time just to upload. */
  skipLocal?: boolean;
}

export interface UploadCasOptions {
  expectedHead: SnapshotId | null;
  expectedRevision: number;
  parentSnapshotIds?: SnapshotId[];
  activate?: boolean;
  requestId?: string;
}

export interface ForkOptions {
  baseSnapshotId: SnapshotId;
  expectedHead: SnapshotId | null;
  expectedRevision: number;
  requestId?: string;
}

export interface SelectBranchOptions {
  expectedHead?: SnapshotId | null;
  expectedRevision?: number;
  requestId?: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

export class ProgressSyncClient<P = unknown> {
  private readonly baseUrl: string;
  private readonly fetchImpl: typeof fetch;
  private readonly token?: string;
  private readonly timeoutMs: number;
  private readonly localStore?: LocalSnapshotStore<P>;
  private readonly headStore?: HeadStateStore;
  private readonly queueStore: OfflineQueueStore;
  private readonly attempts: number;
  private readonly baseDelayMs: number;
  private readonly maxDelayMs: number;
  private readonly sleep: (milliseconds: number) => Promise<void>;
  private readonly now: () => number;
  private readonly idFactory: () => string;
  private readonly known = new Map<WorldId, HeadState>();
  private queueCache: QueuedUpload[] | null = null;
  private queueError: unknown = null;
  private headError: unknown = null;

  constructor(options: ProgressSyncClientOptions<P>) {
    const base = options.baseUrl.replace(/\/+$/, '');
    this.baseUrl = base.endsWith('/local-progress') ? base : `${base}/local-progress`;
    this.fetchImpl = options.fetchImpl ?? ((input, init) => fetch(input, init));
    this.token = options.token;
    this.timeoutMs = options.timeoutMs ?? 10_000;
    this.localStore = options.localStore;
    this.headStore = options.headStore;
    this.queueStore = options.queueStore ?? new MemoryQueueStore();
    this.attempts = Math.max(1, options.retry?.attempts ?? 2);
    this.baseDelayMs = Math.max(0, options.retry?.baseDelayMs ?? 250);
    this.maxDelayMs = Math.max(this.baseDelayMs, options.retry?.maxDelayMs ?? 2_000);
    this.sleep = options.sleep ?? ((milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds)));
    this.now = options.now ?? (() => Date.now());
    this.idFactory = options.idFactory ?? (() => {
      const random = Math.random().toString(36).slice(2, 10);
      return `sync_${this.now().toString(36)}_${random}`;
    });
  }

  /** Last known queue persistence failure, if any. Local saves still succeed. */
  get queuePersistenceError(): unknown {
    return this.queueError;
  }

  /** The snapshot this device last uploaded/read, best-effort (memory then
   * whatever the product persisted). Used by the page to decide whether the
   * remote moved ahead. */
  async lastKnownHead(worldId: WorldId): Promise<HeadState | null> {
    return this.knownHead(worldId);
  }

  /** Last known head-persistence failure, if any. Sync still works this page. */
  get headPersistenceError(): unknown {
    return this.headError;
  }

  async head(worldId: WorldId): Promise<HeadState> {
    const head = await this.request<HeadState>('GET', this.url(`/worlds/${encodeURIComponent(worldId)}/head`), undefined, {
      worldId,
    });
    this.remember(head);
    return head;
  }

  /** Read the remote head without teaching this client that it is in sync.
   * Status checks must not clear the "we may be behind" knowledge. */
  async peekHead(worldId: WorldId): Promise<HeadState> {
    return this.request<HeadState>('GET', this.url(`/worlds/${encodeURIComponent(worldId)}/head`));
  }

  async peekGraph(worldId: WorldId): Promise<GraphState> {
    return this.request<GraphState>('GET', this.url(`/worlds/${encodeURIComponent(worldId)}/graph`));
  }

  async graph(worldId: WorldId): Promise<GraphState> {
    const graph = await this.request<GraphState>('GET', this.url(`/worlds/${encodeURIComponent(worldId)}/graph`), undefined, {
      worldId,
    });
    this.remember(graph);
    return graph;
  }

  async read(worldId: WorldId, snapshotId: SnapshotId): Promise<SnapshotEnvelope<P>> {
    return this.request<SnapshotEnvelope<P>>(
      'GET',
      this.url(`/worlds/${encodeURIComponent(worldId)}/snapshots/${encodeURIComponent(snapshotId)}`),
      undefined,
      { worldId },
    );
  }

  /** 06's local repository is the first writer. No server call is made when
   * `localOnly` is set; a broken server never prevents this call from working. */
  async saveLocal(worldId: WorldId, payload: P): Promise<boolean> {
    if (!this.localStore) return false;
    await this.localStore.save(worldId, payload);
    return true;
  }

  async loadLocal(worldId: WorldId): Promise<P | null> {
    if (!this.localStore) return null;
    return this.localStore.load(worldId);
  }

  /** Save locally, then try the server. Network failures queue instead of throw. */
  async save(worldId: WorldId, payload: P, options: SaveOptions = {}): Promise<SaveOutcome<P>> {
    const known = await this.knownHead(worldId);
    const expectedHead = options.expectedHead !== undefined
      ? options.expectedHead
      : known?.headSnapshotId ?? null;
    const expectedRevision = options.expectedRevision !== undefined
      ? options.expectedRevision
      : known?.revision ?? 0;
    const activate = options.activate ?? true;
    const request: UploadRequest<P> = {
      requestId: options.requestId ?? this.idFactory(),
      parentSnapshotIds: options.parentSnapshotIds
        ?? (activate && expectedHead !== null ? [expectedHead] : []),
      expectedHead,
      expectedRevision,
      activate,
      payload,
    };
    const localSaved = options.skipLocal ? false : await this.saveLocal(worldId, payload);
    if (options.localOnly) return { status: 'local-only', localSaved, request };

    // Do not send a newer save ahead of an older unsynced save for the same
    // world. The later payload is complete state, but ordering still matters
    // for CAS; it is queued behind the earlier request and rebased at flush.
    const pending = await this.lastQueued(worldId);
    if (pending) {
      await this.enqueue(worldId, request, {
        previousRequestId: pending.request.activate && activate ? pending.request.requestId : null,
        sent: false,
      });
      return {
        status: 'queued',
        localSaved,
        request,
        reason: 'queued_behind',
        message: 'queued behind an earlier unsynced save; call flush() after reconnecting',
      };
    }

    try {
      const upload = await this.withRetry(() => this.postUpload(worldId, request));
      return { status: 'synced', localSaved, upload };
    } catch (error) {
      if (error instanceof ProgressConflictError) {
        return { status: 'conflict', localSaved, conflict: error as ProgressConflictErrorType<P> };
      }
      if (error instanceof ProgressSyncError && error.retryable) {
        await this.enqueue(worldId, request, { sent: true });
        return {
          status: 'queued',
          localSaved,
          request,
          reason: error.code === 'network_error' ? 'offline' : 'server_error',
          message: error.message,
        };
      }
      throw error;
    }
  }

  /** Raw conditional upload. The caller supplies both CAS values. */
  async uploadCAS(worldId: WorldId, payload: P, options: UploadCasOptions): Promise<UploadResult> {
    const activate = options.activate ?? true;
    const request: UploadRequest<P> = {
      requestId: options.requestId ?? this.idFactory(),
      parentSnapshotIds: options.parentSnapshotIds
        ?? (activate && options.expectedHead !== null ? [options.expectedHead] : []),
      expectedHead: options.expectedHead,
      expectedRevision: options.expectedRevision,
      activate,
      payload,
    };
    return this.withRetry(() => this.postUpload(worldId, request));
  }

  /** Store a child of `baseSnapshotId` without moving the active head. */
  async fork(worldId: WorldId, payload: P, options: ForkOptions): Promise<UploadResult> {
    return this.uploadCAS(worldId, payload, {
      expectedHead: options.expectedHead,
      expectedRevision: options.expectedRevision,
      parentSnapshotIds: [options.baseSnapshotId],
      activate: false,
      requestId: options.requestId,
    });
  }

  /** Move the active head to a stored branch leaf. This never rewrites payloads. */
  async selectBranch(
    worldId: WorldId,
    snapshotId: SnapshotId,
    options: SelectBranchOptions = {},
  ): Promise<SelectHeadResult> {
    let expectedHead = options.expectedHead;
    let expectedRevision = options.expectedRevision;
    if (expectedHead === undefined || expectedRevision === undefined) {
      const current = await this.head(worldId);
      expectedHead ??= current.headSnapshotId;
      expectedRevision ??= current.revision;
    }
    const request: SelectHeadRequest = {
      requestId: options.requestId ?? this.idFactory(),
      snapshotId,
      expectedHead: expectedHead ?? null,
      expectedRevision: expectedRevision ?? 0,
    };
    const result = await this.withRetry(() => this.request<SelectHeadResult>(
      'POST',
      this.url(`/worlds/${encodeURIComponent(worldId)}/head`),
      request,
      { worldId },
    ));
    this.remember(result);
    return result;
  }

  /** Two-device recovery: read the active head and write it into 06's store. */
  async pullLatest(worldId: WorldId, options: { saveLocal?: boolean } = {}): Promise<PullResult<P>> {
    const head = await this.head(worldId);
    if (!head.headSnapshotId) return { head, snapshot: null, localSaved: false };
    const snapshot = await this.read(worldId, head.headSnapshotId);
    // A product whose session owns the durable store must not have a second
    // writer; it reads the remote copy and opens it itself.
    const localSaved = options.saveLocal === false
      ? false
      : await this.saveLocal(worldId, snapshot.payload);
    return { head, snapshot, localSaved };
  }

  async pullSnapshot(
    worldId: WorldId,
    snapshotId: SnapshotId,
    options: { saveLocal?: boolean } = {},
  ): Promise<PullResult<P>> {
    const snapshot = await this.read(worldId, snapshotId);
    const localSaved = options.saveLocal === false
      ? false
      : await this.saveLocal(worldId, snapshot.payload);
    return { head: this.known.get(worldId) ?? { worldId, headSnapshotId: null, revision: 0 }, snapshot, localSaved };
  }

  async pending(): Promise<number> {
    return (await this.loadQueue()).length;
  }

  /** Retry queued uploads. Conflicts stay queued for an explicit branch choice. */
  async flush(): Promise<FlushOutcome<P>> {
    const items = await this.loadQueue();
    const remaining: QueuedUpload[] = [];
    const uploaded: UploadResult[] = [];
    const conflicts: FlushConflict<P>[] = [];
    const failures: FlushOutcome<P>['failures'] = [];
    const resolved = new Map<string, UploadResult>();
    let offline = false;

    for (const item of items) {
      if (offline) {
        remaining.push(item);
        continue;
      }
      let request = item.request as UploadRequest<P>;
      if (item.previousRequestId) {
        if (item.sent !== false) {
          failures.push({
            requestId: request.requestId,
            code: 'dependency_not_rewritable',
            message: 'a queued request that may already have reached the server cannot be rebased',
          });
          remaining.push(item);
          continue;
        }
        const previous = resolved.get(item.previousRequestId);
        if (!previous) {
          failures.push({
            requestId: request.requestId,
            code: 'dependency_missing',
            message: `earlier queued request ${item.previousRequestId} has not been resolved`,
          });
          remaining.push(item);
          continue;
        }
        // This body was never sent (sent=false), so replacing its stale CAS
        // values with the predecessor's result cannot break idempotency.
        request = this.rebaseRequest(request, previous);
        item.request = request as UploadRequest;
        item.previousRequestId = null;
        item.sent = false;
      }
      try {
        const result = await this.withRetry(() => this.postUpload(item.worldId, request));
        resolved.set(item.request.requestId, result);
        uploaded.push(result);
      } catch (error) {
        if (error instanceof ProgressConflictError) {
          conflicts.push({ requestId: request.requestId, conflict: error as ProgressConflictErrorType<P> });
          remaining.push(item);
        } else if (error instanceof ProgressSyncError && error.retryable) {
          offline = error.code === 'network_error';
          remaining.push({ ...item, attempts: item.attempts + 1 });
        } else {
          const syncError = error instanceof ProgressSyncError ? error : null;
          failures.push({
            requestId: request.requestId,
            code: syncError?.code ?? 'unknown_error',
            message: error instanceof Error ? error.message : String(error),
          });
          remaining.push(item);
        }
      }
    }

    // If the connection dropped before a chained item was attempted, still
    // persist the rebase so the next flush does not lose the predecessor link.
    for (const item of remaining) {
      if (!item.previousRequestId) continue;
      const previous = resolved.get(item.previousRequestId);
      if (!previous) continue;
      item.request = this.rebaseRequest(item.request as UploadRequest<P>, previous) as UploadRequest;
      item.previousRequestId = null;
      item.sent = false;
    }

    await this.persistQueue(remaining);
    return { uploaded, conflicts, failures, remaining: remaining.length, offline };
  }

  async dropQueued(requestId: string): Promise<boolean> {
    const items = await this.loadQueue();
    const next = items.filter((item) => item.request.requestId !== requestId);
    if (next.length === items.length) return false;
    await this.persistQueue(next);
    return true;
  }

  /** Resolve a queued conflict after the player explicitly picks a branch. */
  async resolveQueuedConflict(requestId: string, choice: ConflictChoice): Promise<ResolveResult<P>> {
    const items = await this.loadQueue();
    const item = items.find((entry) => entry.request.requestId === requestId);
    if (!item || !item.worldId) {
      throw new ProgressSyncError(`queued request ${requestId} not found`, 'queued_request_not_found', 0);
    }
    const current = await this.head(item.worldId);
    const conflict = new ProgressConflictError<P>(
      'queued upload conflicts with the current head',
      'queued_conflict',
      item.worldId,
      current,
      [],
      item.request as UploadRequest<P>,
    );
    const result = await this.resolveConflict(conflict, choice);
    const after = await this.loadQueue();
    const next = after.filter((entry) => entry.request.requestId !== requestId);
    if (choice === 'keep-local-fork' && result.head.headSnapshotId) {
      for (const entry of next) {
        if (entry.previousRequestId !== requestId) continue;
        entry.request = this.rebaseRequest(entry.request as UploadRequest<P>, result.head) as UploadRequest;
        entry.previousRequestId = null;
        entry.sent = false;
      }
    }
    await this.persistQueue(next);
    return result;
  }

  /**
   * Explicit conflict resolution.
   * - keep-remote: pull the active remote branch into the local store.
   * - keep-local-fork: store the local payload as a fork of its old base, then
   *   select it. The rejected remote branch remains stored and readable.
   */
  async resolveConflict(
    conflict: ProgressConflictErrorType<P>,
    choice: ConflictChoice,
    options: { saveLocal?: boolean } = {},
  ): Promise<ResolveResult<P>> {
    if (choice === 'keep-remote') {
      const pulled = await this.pullLatest(conflict.worldId, { saveLocal: options.saveLocal });
      return {
        status: 'remote',
        head: pulled.head,
        snapshot: pulled.snapshot,
        localSaved: pulled.localSaved,
      };
    }

    const request = conflict.request;
    if (!request) {
      throw new ProgressSyncError(
        'this conflict carries no local upload to preserve',
        'conflict_without_local',
        0,
      );
    }
    const current = await this.head(conflict.worldId);
    const baseParents = request.parentSnapshotIds.length
      ? [...request.parentSnapshotIds]
      : current.headSnapshotId
        ? [current.headSnapshotId]
        : [];

    if (!baseParents.length && current.headSnapshotId === null) {
      const upload = await this.uploadCAS(conflict.worldId, request.payload, {
        expectedHead: null,
        expectedRevision: current.revision,
        parentSnapshotIds: [],
        activate: true,
        requestId: this.childRequestId(request.requestId, 'fork'),
      });
      const pulled = await this.pullLatest(conflict.worldId, { saveLocal: options.saveLocal });
      return {
        status: 'local-fork',
        head: pulled.head,
        snapshot: pulled.snapshot,
        localSaved: pulled.localSaved,
        upload,
      };
    }

    const fork = await this.uploadCAS(conflict.worldId, request.payload, {
      expectedHead: current.headSnapshotId,
      expectedRevision: current.revision,
      parentSnapshotIds: baseParents,
      activate: false,
      requestId: this.childRequestId(request.requestId, 'fork'),
    });
    await this.selectBranch(conflict.worldId, fork.snapshotId, {
      expectedHead: fork.headSnapshotId,
      expectedRevision: fork.revision,
      requestId: this.childRequestId(request.requestId, 'select'),
    });
    const pulled = await this.pullLatest(conflict.worldId, { saveLocal: options.saveLocal });
    return {
      status: 'local-fork',
      head: pulled.head,
      snapshot: pulled.snapshot,
      localSaved: pulled.localSaved,
      upload: fork,
    };
  }

  // -- internals -----------------------------------------------------------

  private url(path: string): string {
    return `${this.baseUrl}${path}`;
  }

  private remember(head: HeadState): void {
    const entry: HeadState = {
      worldId: head.worldId,
      headSnapshotId: head.headSnapshotId,
      revision: head.revision,
      updatedAt: head.updatedAt,
    };
    this.known.set(head.worldId, entry);
    void this.persistHead(entry);
  }

  private async persistHead(head: HeadState): Promise<void> {
    if (!this.headStore) return;
    try {
      await this.headStore.save(head.worldId, head);
      this.headError = null;
    } catch (error) {
      this.headError = error;
    }
  }

  /** In-memory knowledge first, then whatever the product persisted. */
  private async knownHead(worldId: WorldId): Promise<HeadState | null> {
    const cached = this.known.get(worldId);
    if (cached) return cached;
    if (!this.headStore) return null;
    try {
      const stored = await this.headStore.load(worldId);
      if (!stored || typeof stored.revision !== 'number' || stored.headSnapshotId === undefined) return null;
      const entry: HeadState = {
        worldId: stored.worldId || worldId,
        headSnapshotId: stored.headSnapshotId ?? null,
        revision: stored.revision,
        updatedAt: stored.updatedAt ?? null,
      };
      this.known.set(worldId, entry);
      return entry;
    } catch (error) {
      this.headError = error;
      return null;
    }
  }

  private childRequestId(base: string, suffix: string): string {
    return `${base.slice(0, 190)}:${suffix}`;
  }

  private async postUpload(worldId: WorldId, request: UploadRequest<P>): Promise<UploadResult> {
    const result = await this.request<UploadResult>(
      'POST',
      this.url(`/worlds/${encodeURIComponent(worldId)}/snapshots`),
      request,
      { worldId, conflictRequest: request },
    );
    this.remember(result);
    return result;
  }

  private async withRetry<T>(operation: () => Promise<T>): Promise<T> {
    let lastError: unknown;
    for (let attempt = 0; attempt < this.attempts; attempt += 1) {
      try {
        return await operation();
      } catch (error) {
        lastError = error;
        if (!(error instanceof ProgressSyncError) || !error.retryable || attempt >= this.attempts - 1) {
          throw error;
        }
        const delay = Math.min(this.maxDelayMs, this.baseDelayMs * 2 ** attempt);
        await this.sleep(delay);
      }
    }
    throw lastError;
  }

  private async request<T>(
    method: 'GET' | 'POST',
    path: string,
    body?: unknown,
    options: { worldId?: WorldId; conflictRequest?: UploadRequest<P> | null } = {},
  ): Promise<T> {
    let bodyText: string | undefined;
    if (body !== undefined) {
      try {
        bodyText = JSON.stringify(body);
      } catch (error) {
        throw new ProgressSyncError(
          `request body is not JSON serializable: ${error instanceof Error ? error.message : String(error)}`,
          'request_malformed',
          0,
        );
      }
    }
    const headers: Record<string, string> = { Accept: 'application/json' };
    if (bodyText !== undefined) headers['Content-Type'] = 'application/json';
    if (this.token) headers.Authorization = `Bearer ${this.token}`;

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    let response: Response;
    try {
      response = await this.fetchImpl(path, {
        method,
        headers,
        body: bodyText,
        signal: controller.signal,
      });
    } catch (error) {
      throw new ProgressSyncError(
        `progress service is unreachable: ${error instanceof Error ? error.message : String(error)}`,
        'network_error',
        0,
        { retryable: true, details: error },
      );
    } finally {
      clearTimeout(timer);
    }

    const text = await response.text();
    let parsed: unknown = null;
    if (text) {
      try {
        parsed = JSON.parse(text) as unknown;
      } catch {
        throw new ProgressSyncError(
          `progress service returned non-JSON (${response.status})`,
          'invalid_response',
          response.status,
          { retryable: response.status >= 500, details: text.slice(0, 500) },
        );
      }
    }

    if (!response.ok) {
      const detail = isRecord(parsed) && isRecord(parsed.detail) ? parsed.detail : {};
      const code = typeof detail.code === 'string' ? detail.code : `http_${response.status}`;
      const message = typeof detail.message === 'string'
        ? detail.message
        : `progress service rejected the request (${response.status})`;
      if (response.status === 409) {
        const head = isRecord(detail.head) ? detail.head : {};
        const remote: HeadState = {
          worldId: typeof head.worldId === 'string' ? head.worldId : options.worldId ?? '',
          headSnapshotId: typeof head.headSnapshotId === 'string' ? head.headSnapshotId : null,
          revision: typeof head.revision === 'number' ? head.revision : 0,
          updatedAt: typeof head.updatedAt === 'string' ? head.updatedAt : null,
        };
        const branches = Array.isArray(detail.branches)
          ? detail.branches.filter((id): id is string => typeof id === 'string')
          : [];
        throw new ProgressConflictError<P>(
          message,
          code,
          remote.worldId || options.worldId || '',
          remote,
          branches,
          options.conflictRequest ?? null,
        );
      }
      throw new ProgressSyncError(message, code, response.status, {
        retryable: response.status >= 500 || response.status === 429,
        details: parsed,
      });
    }

    return parsed as T;
  }

  private async loadQueue(): Promise<QueuedUpload[]> {
    if (this.queueCache) return this.queueCache;
    try {
      const items = await this.queueStore.load();
      this.queueCache = items.filter((item) => Boolean(item)
        && typeof item.worldId === 'string'
        && typeof item.request?.requestId === 'string');
    } catch (error) {
      this.queueCache = [];
      this.queueError = error;
    }
    return this.queueCache;
  }

  private async persistQueue(items: readonly QueuedUpload[]): Promise<void> {
    this.queueCache = items.map((item) => ({ ...item }));
    try {
      await this.queueStore.save(items);
      this.queueError = null;
    } catch (error) {
      // Keep the in-memory queue so the current page can still retry.
      this.queueError = error;
    }
  }

  private async enqueue(
    worldId: WorldId,
    request: UploadRequest<P>,
    options: { previousRequestId?: string | null; sent: boolean },
  ): Promise<void> {
    const items = await this.loadQueue();
    if (items.some((item) => item.request.requestId === request.requestId)) return;
    const next = [...items, {
      worldId,
      request: request as UploadRequest,
      previousRequestId: options.previousRequestId ?? null,
      sent: options.sent,
      attempts: 0,
      createdAt: new Date(this.now()).toISOString(),
    }];
    await this.persistQueue(next);
  }

  private async lastQueued(worldId: WorldId): Promise<QueuedUpload | null> {
    const items = await this.loadQueue();
    for (let index = items.length - 1; index >= 0; index -= 1) {
      if (items[index].worldId === worldId) return items[index];
    }
    return null;
  }

  /** Replace stale CAS values with the previous queued upload's result. */
  private rebaseRequest(
    request: UploadRequest<P>,
    previous: Pick<HeadState, 'headSnapshotId' | 'revision'>,
  ): UploadRequest<P> {
    if (!request.activate) return request;
    return {
      ...request,
      expectedHead: previous.headSnapshotId,
      expectedRevision: previous.revision,
      parentSnapshotIds: previous.headSnapshotId ? [previous.headSnapshotId] : [],
    };
  }
}
