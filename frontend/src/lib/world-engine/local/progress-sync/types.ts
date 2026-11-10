/** Wire and client types for progress sync.
 *
 * `payload` is the opaque LocalGameSnapshot already produced by the browser
 * session. These types intentionally do not import or describe WorldState.
 */

export type SnapshotId = string;
export type WorldId = string;

export interface HeadState {
  worldId: WorldId;
  headSnapshotId: SnapshotId | null;
  revision: number;
  updatedAt?: string | null;
}

export interface SnapshotSummary {
  snapshotId: SnapshotId;
  parentSnapshotIds: SnapshotId[];
  contentDigest: string;
  sizeBytes: number;
  createdAt: string;
}

export interface SnapshotEnvelope<P = unknown> extends SnapshotSummary {
  payload: P;
}

export interface GraphState extends HeadState {
  nodes: SnapshotSummary[];
  branches: SnapshotId[];
}

export interface UploadRequest<P = unknown> {
  requestId: string;
  parentSnapshotIds: SnapshotId[];
  expectedHead: SnapshotId | null;
  expectedRevision: number;
  /** true advances the active head; false stores an explicit fork only. */
  activate: boolean;
  payload: P;
}

export interface UploadResult extends HeadState {
  snapshotId: SnapshotId;
  contentDigest: string;
  parentSnapshotIds: SnapshotId[];
  created: boolean;
  changed: boolean;
  idempotent: boolean;
}

export interface SelectHeadRequest {
  requestId: string;
  snapshotId: SnapshotId;
  expectedHead: SnapshotId | null;
  expectedRevision: number;
}

export interface SelectHeadResult extends HeadState {
  previousHeadSnapshotId: SnapshotId | null;
  changed: boolean;
  idempotent: boolean;
}

/** 06 owns the local repository. The sync client consumes these two calls and
 * never writes that repository's files directly. */
export interface LocalSnapshotStore<P = unknown> {
  load(worldId: WorldId): Promise<P | null>;
  save(worldId: WorldId, payload: P): Promise<void>;
}

export interface QueuedUpload<P = unknown> {
  worldId: WorldId;
  request: UploadRequest<P>;
  /** Set when this save was made while an earlier save for the same world was
   * still queued. The flush rebases it onto the earlier upload's result. */
  previousRequestId?: string | null;
  /** false means this exact body was never sent, so rebasing is safe. */
  sent?: boolean;
  attempts: number;
  createdAt: string;
}

export interface OfflineQueueStore {
  load(): Promise<QueuedUpload[]>;
  save(items: readonly QueuedUpload[]): Promise<void>;
}

export type ConflictChoice = 'keep-remote' | 'keep-local-fork';

export type SaveOutcome<P = unknown> =
  | { status: 'synced'; localSaved: boolean; upload: UploadResult }
  | { status: 'local-only'; localSaved: boolean; request: UploadRequest<P> }
  | { status: 'queued'; localSaved: boolean; request: UploadRequest<P>; reason: 'offline' | 'server_error' | 'queued_behind'; message: string }
  | { status: 'conflict'; localSaved: boolean; conflict: ProgressConflictError<P> };

export interface FlushConflict<P = unknown> {
  requestId: string;
  conflict: ProgressConflictError<P>;
}

export interface FlushOutcome<P = unknown> {
  uploaded: UploadResult[];
  conflicts: FlushConflict<P>[];
  failures: Array<{ requestId: string; code: string; message: string }>;
  remaining: number;
  offline: boolean;
}

export interface PullResult<P = unknown> {
  head: HeadState;
  snapshot: SnapshotEnvelope<P> | null;
  localSaved: boolean;
}

export interface ResolveResult<P = unknown> {
  status: 'remote' | 'local-fork';
  head: HeadState;
  snapshot: SnapshotEnvelope<P> | null;
  localSaved: boolean;
  upload?: UploadResult;
}

export class ProgressSyncError extends Error {
  readonly code: string;
  readonly status: number;
  readonly retryable: boolean;
  readonly details: unknown;

  constructor(
    message: string,
    code: string,
    status = 0,
    options: { retryable?: boolean; details?: unknown } = {},
  ) {
    super(message);
    this.name = 'ProgressSyncError';
    this.code = code;
    this.status = status;
    this.retryable = options.retryable ?? false;
    this.details = options.details;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/** A 409 from the server. `remote` is the authoritative head at rejection
 * time; `branches` tells the caller which branches could be selected. */
export class ProgressConflictError<P = unknown> extends ProgressSyncError {
  readonly worldId: WorldId;
  readonly remote: HeadState;
  readonly branches: SnapshotId[];
  readonly request: UploadRequest<P> | null;

  constructor(
    message: string,
    code: string,
    worldId: WorldId,
    remote: HeadState,
    branches: SnapshotId[],
    request: UploadRequest<P> | null,
    status = 409,
  ) {
    super(message, code, status, { details: { remote, branches } });
    this.name = 'ProgressConflictError';
    this.worldId = worldId;
    this.remote = remote;
    this.branches = branches;
    this.request = request;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}
