import { createHash } from 'node:crypto';
import { describe, expect, it } from 'vitest';

import {
  ProgressSyncClient,
  ProgressSyncError,
  compareLineage,
  createProductSync,
  createWebStorageHeadStore,
  createWebStorageQueueStore,
  MemoryQueueStore,
  type HeadState,
  type HeadStateStore,
  type LocalSnapshotStore,
  type OfflineQueueStore,
  type UploadRequest,
} from './index';

interface FakeNode {
  snapshotId: string;
  parentSnapshotIds: string[];
  contentDigest: string;
  sizeBytes: number;
  createdAt: string;
  payload: unknown;
}

interface FakeWorld {
  headSnapshotId: string | null;
  revision: number;
  nodes: Map<string, FakeNode>;
  requests: Map<string, { hash: string; response: Record<string, unknown> }>;
}

interface Call {
  method: string;
  path: string;
  body: unknown;
  status: number;
}

function canonical(value: unknown): string {
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  const record = value as Record<string, unknown>;
  return `{${Object.keys(record).sort().map((key) => `${JSON.stringify(key)}:${canonical(record[key])}`).join(',')}}`;
}

function digest(value: unknown): string {
  return createHash('sha256').update(canonical(value)).digest('hex');
}

class FakeProgressServer {
  readonly worlds = new Map<string, FakeWorld>();
  readonly calls: Call[] = [];
  offline = false;
  loseNextUploadResponse = false;
  failNextWith500 = false;

  fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = new URL(typeof input === 'string' ? input : input.toString());
    const method = init?.method ?? 'GET';
    const rawBody = init?.body ? JSON.parse(String(init.body)) as Record<string, unknown> : null;
    if (this.offline) throw new TypeError('fetch failed: offline');
    if (this.failNextWith500) {
      this.failNextWith500 = false;
      this.calls.push({ method, path: url.pathname, body: rawBody, status: 500 });
      return this.json(500, { detail: { code: 'server_error', message: 'temporary failure' } });
    }
    const parts = url.pathname.split('/').filter(Boolean);
    // ['local-progress', 'worlds', worldId, ...]
    if (parts[0] !== 'local-progress' || parts[1] !== 'worlds') {
      return this.json(404, { detail: { code: 'not_found' } });
    }
    const worldId = decodeURIComponent(parts[2]);
    const tail = parts.slice(3);
    let status = 200;
    let body: unknown;
    try {
      if (method === 'GET' && tail.length === 1 && tail[0] === 'head') body = this.head(worldId);
      else if (method === 'GET' && tail.length === 1 && tail[0] === 'graph') body = this.graph(worldId);
      else if (method === 'GET' && tail[0] === 'snapshots' && tail.length === 2) {
        body = this.read(worldId, decodeURIComponent(tail[1]));
      } else if (method === 'POST' && tail.length === 1 && tail[0] === 'snapshots') {
        const result = this.upload(worldId, rawBody as unknown as UploadRequest);
        status = result.status;
        body = result.body;
      } else if (method === 'POST' && tail.length === 1 && tail[0] === 'head') {
        const result = this.select(worldId, rawBody as Record<string, unknown>);
        status = result.status;
        body = result.body;
      } else {
        status = 404;
        body = { detail: { code: 'not_found' } };
      }
    } catch (error) {
      const failure = error as { status?: number; code?: string; message?: string; head?: unknown; branches?: unknown };
      status = failure.status ?? 500;
      body = {
        detail: {
          code: failure.code ?? 'server_error',
          message: failure.message ?? 'failed',
          ...(failure.head ? { head: failure.head } : {}),
          ...(failure.branches ? { branches: failure.branches } : {}),
        },
      };
    }
    this.calls.push({ method, path: url.pathname, body: rawBody, status });
    if (method === 'POST' && tail[0] === 'snapshots' && this.loseNextUploadResponse) {
      this.loseNextUploadResponse = false;
      throw new TypeError('fetch failed after apply');
    }
    return this.json(status, body);
  };

  seed(worldId: string, payload: unknown): FakeNode {
    const result = this.upload(worldId, {
      requestId: `seed-${digest(payload).slice(0, 8)}`,
      parentSnapshotIds: [],
      expectedHead: null,
      expectedRevision: 0,
      activate: true,
      payload,
    });
    if (result.status !== 201) throw new Error(`seed failed: ${JSON.stringify(result.body)}`);
    return this.worlds.get(worldId)!.nodes.get((result.body as { snapshotId: string }).snapshotId)!;
  }

  private world(worldId: string, create = false): FakeWorld {
    let world = this.worlds.get(worldId);
    if (!world) {
      if (!create) throw this.failure(404, 'world_not_found', `world ${worldId} not found`);
      world = { headSnapshotId: null, revision: 0, nodes: new Map(), requests: new Map() };
      this.worlds.set(worldId, world);
    }
    return world;
  }

  private head(worldId: string) {
    const world = this.world(worldId);
    return { worldId, headSnapshotId: world.headSnapshotId, revision: world.revision };
  }

  private graph(worldId: string) {
    const world = this.world(worldId);
    const parents = new Set<string>();
    for (const node of world.nodes.values()) for (const parent of node.parentSnapshotIds) parents.add(parent);
    return {
      ...this.head(worldId),
      nodes: [...world.nodes.values()]
        .sort((a, b) => a.createdAt.localeCompare(b.createdAt) || a.snapshotId.localeCompare(b.snapshotId))
        .map((node) => ({
          snapshotId: node.snapshotId,
          parentSnapshotIds: node.parentSnapshotIds,
          contentDigest: node.contentDigest,
          sizeBytes: node.sizeBytes,
          createdAt: node.createdAt,
        })),
      branches: [...world.nodes.keys()].filter((id) => !parents.has(id)).sort(),
    };
  }

  private read(worldId: string, snapshotId: string) {
    const world = this.world(worldId);
    const node = world.nodes.get(snapshotId);
    if (!node) throw this.failure(404, 'snapshot_not_found', `snapshot ${snapshotId} not found`);
    return node;
  }

  private upload(worldId: string, request: UploadRequest): { status: number; body: unknown } {
    const world = this.world(worldId, true);
    const hash = JSON.stringify(request);
    const cached = world.requests.get(request.requestId);
    if (cached) {
      if (cached.hash !== hash) throw this.failure(409, 'request_id_reused', 'requestId reused');
      return {
        status: 200,
        body: { ...cached.response, headSnapshotId: world.headSnapshotId, revision: world.revision, changed: false, idempotent: true },
      };
    }
    if (request.expectedRevision !== world.revision) {
      throw this.failure(409, 'revision_mismatch', 'stale revision', this.head(worldId), []);
    }
    if (request.expectedHead !== world.headSnapshotId) {
      throw this.failure(409, 'head_mismatch', 'stale head', this.head(worldId), []);
    }
    const contentDigest = digest(request.payload);
    const parents = [...new Set(request.parentSnapshotIds)].sort();
    for (const parent of parents) {
      if (!world.nodes.has(parent)) throw this.failure(400, 'parent_unknown', `parent ${parent} missing`);
    }
    if (request.activate && world.headSnapshotId && !parents.includes(world.headSnapshotId)) {
      throw this.failure(400, 'request_malformed', 'activating upload must name current head');
    }
    const headNode = world.headSnapshotId ? world.nodes.get(world.headSnapshotId) : null;
    if (request.activate && headNode && headNode.contentDigest === contentDigest) {
      const body = {
        worldId,
        snapshotId: headNode.snapshotId,
        contentDigest,
        parentSnapshotIds: headNode.parentSnapshotIds,
        headSnapshotId: world.headSnapshotId,
        revision: world.revision,
        created: false,
        changed: false,
        idempotent: false,
      };
      world.requests.set(request.requestId, { hash, response: body });
      return { status: 200, body };
    }
    const snapshotId = `snap_${digest({ worldId, contentDigest, parentSnapshotIds: parents })}`;
    let node = world.nodes.get(snapshotId);
    let created = false;
    if (!node) {
      node = {
        snapshotId,
        parentSnapshotIds: parents,
        contentDigest,
        sizeBytes: Buffer.byteLength(canonical(request.payload)),
        createdAt: new Date(1_700_000_000_000 + world.nodes.size).toISOString(),
        payload: request.payload,
      };
      world.nodes.set(snapshotId, node);
      created = true;
    }
    const newHead = request.activate ? snapshotId : world.headSnapshotId;
    const changed = created || newHead !== world.headSnapshotId;
    if (changed) {
      world.revision += 1;
      world.headSnapshotId = newHead;
    }
    const body = {
      worldId,
      snapshotId,
      contentDigest,
      parentSnapshotIds: node.parentSnapshotIds,
      headSnapshotId: world.headSnapshotId,
      revision: world.revision,
      created,
      changed,
      idempotent: false,
    };
    world.requests.set(request.requestId, { hash, response: body });
    return { status: created ? 201 : 200, body };
  }

  private select(worldId: string, request: Record<string, unknown>): { status: number; body: unknown } {
    const world = this.world(worldId);
    const id = String(request.snapshotId);
    if (!world.nodes.has(id)) throw this.failure(404, 'snapshot_not_found', 'missing');
    if (request.expectedRevision !== world.revision) {
      throw this.failure(409, 'revision_mismatch', 'stale revision', this.head(worldId), []);
    }
    if (request.expectedHead !== world.headSnapshotId) {
      throw this.failure(409, 'head_mismatch', 'stale head', this.head(worldId), []);
    }
    const hasChildren = [...world.nodes.values()].some((node) => node.parentSnapshotIds.includes(id));
    if (hasChildren && id !== world.headSnapshotId) {
      throw this.failure(409, 'not_branch_leaf', 'not a leaf', this.head(worldId), []);
    }
    const previous = world.headSnapshotId;
    const changed = previous !== id;
    if (changed) {
      world.headSnapshotId = id;
      world.revision += 1;
    }
    return {
      status: 200,
      body: {
        worldId,
        headSnapshotId: world.headSnapshotId,
        previousHeadSnapshotId: previous,
        revision: world.revision,
        changed,
        idempotent: false,
      },
    };
  }

  private failure(status: number, code: string, message: string, head?: unknown, branches?: unknown) {
    return Object.assign(new Error(message), { status, code, head, branches });
  }

  private json(status: number, body: unknown): Response {
    return new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}

class MemoryLocalStore implements LocalSnapshotStore<unknown> {
  readonly values = new Map<string, unknown>();
  readonly saves: Array<{ worldId: string; payload: unknown }> = [];

  async load(worldId: string): Promise<unknown | null> {
    return this.values.get(worldId) ?? null;
  }

  async save(worldId: string, payload: unknown): Promise<void> {
    this.values.set(worldId, structuredClone(payload));
    this.saves.push({ worldId, payload: structuredClone(payload) });
  }
}

class MemoryHeadStore implements HeadStateStore {
  readonly values = new Map<string, HeadState>();
  async load(worldId: string): Promise<HeadState | null> {
    const stored = this.values.get(worldId);
    return stored ? structuredClone(stored) : null;
  }
  async save(worldId: string, head: HeadState): Promise<void> {
    this.values.set(worldId, structuredClone(head));
  }
}

function makeClient(
  server: FakeProgressServer,
  localStore: MemoryLocalStore = new MemoryLocalStore(),
  queueStore: OfflineQueueStore = new MemoryQueueStore(),
  headStore: HeadStateStore | null = null,
): { client: ProgressSyncClient<unknown>; localStore: MemoryLocalStore; queueStore: OfflineQueueStore } {
  let counter = 0;
  return {
    client: new ProgressSyncClient<unknown>({
      baseUrl: 'http://sync.test',
      fetchImpl: server.fetch,
      localStore,
      headStore: headStore ?? undefined,
      queueStore,
      retry: { attempts: 1, baseDelayMs: 0 },
      sleep: async () => undefined,
      now: () => 1_700_000_000_000,
      idFactory: () => `test-${++counter}`,
    }),
    localStore,
    queueStore,
  };
}

const snapshot = (turn: number, text = '门厅里很安静。') => ({
  transport: { worldId: 'w1', round: turn, state: { characters: { a: { position: 'hall' } } } },
  commands: [text],
});

describe('ProgressSyncClient', () => {
  it('saves locally first, then uploads with CAS and reads back the opaque payload', async () => {
    const server = new FakeProgressServer();
    const { client, localStore } = makeClient(server);

    const outcome = await client.save('w1', snapshot(1), { requestId: 'save-1' });
    expect(outcome.status).toBe('synced');
    expect(localStore.values.get('w1')).toEqual(snapshot(1));
    if (outcome.status !== 'synced') throw new Error('expected sync');
    expect(outcome.upload.revision).toBe(1);
    expect(outcome.upload.headSnapshotId).toBe(outcome.upload.snapshotId);

    const head = await client.head('w1');
    expect(head.headSnapshotId).toBe(outcome.upload.snapshotId);
    const read = await client.read('w1', head.headSnapshotId!);
    expect(read.payload).toEqual(snapshot(1));
  });

  it('does not move local play behind the server and returns stale CAS as conflict', async () => {
    const server = new FakeProgressServer();
    const deviceA = makeClient(server);
    const root = await deviceA.client.save('w1', snapshot(1), { requestId: 'a1' });
    if (root.status !== 'synced') throw new Error('root failed');
    const second = await deviceA.client.save('w1', snapshot(2), { requestId: 'a2' });
    if (second.status !== 'synced') throw new Error('second failed');

    const deviceB = makeClient(server);
    const stale = await deviceB.client.save('w1', snapshot(2, 'B离线内容'), {
      requestId: 'b-stale',
      expectedHead: root.upload.snapshotId,
      expectedRevision: root.upload.revision,
    });
    expect(stale.status).toBe('conflict');
    if (stale.status !== 'conflict') throw new Error('expected conflict');
    expect(stale.conflict.code).toBe('revision_mismatch');
    expect(stale.conflict.remote.headSnapshotId).toBe(second.upload.snapshotId);
    expect(stale.conflict.remote.revision).toBe(2);
    expect(deviceB.localStore.values.get('w1')).toEqual(snapshot(2, 'B离线内容'));

    const head = await deviceA.client.head('w1');
    expect(head.headSnapshotId).toBe(second.upload.snapshotId);
  });

  it('remembers the saved head across a reload so an offline save still descends from it', async () => {
    const server = new FakeProgressServer();
    const localStore = new MemoryLocalStore();
    const headStore = new MemoryHeadStore();
    const first = makeClient(server, localStore, new MemoryQueueStore(), headStore);
    const root = await first.client.save('w1', snapshot(1), { requestId: 'reload-root' });
    if (root.status !== 'synced') throw new Error('root failed');
    expect(headStore.values.get('w1')?.headSnapshotId).toBe(root.upload.snapshotId);
    expect(headStore.values.get('w1')?.revision).toBe(1);

    // A reload: new client, same persisted local save + head, server unreachable.
    server.offline = true;
    const reloaded = makeClient(server, localStore, new MemoryQueueStore(), headStore);
    const offline = await reloaded.client.save('w1', snapshot(2), { requestId: 'reload-2' });
    expect(offline.status).toBe('queued');
    if (offline.status !== 'queued') throw new Error('expected queued');
    // The queued request names the stored head, not an empty world.
    expect(offline.request.expectedHead).toBe(root.upload.snapshotId);
    expect(offline.request.expectedRevision).toBe(1);
    expect(offline.request.parentSnapshotIds).toEqual([root.upload.snapshotId]);

    server.offline = false;
    const flushed = await reloaded.client.flush();
    expect(flushed.conflicts).toHaveLength(0);
    expect(flushed.uploaded).toHaveLength(1);
    expect(server.worlds.get('w1')!.revision).toBe(2);
    expect(server.worlds.get('w1')!.headSnapshotId).toBe(flushed.uploaded[0].snapshotId);
  });

  it('queues offline saves and flushes them with the same requestId', async () => {
    const server = new FakeProgressServer();
    const { client } = makeClient(server);
    server.offline = true;

    const offline = await client.save('w1', snapshot(1), { requestId: 'offline-1' });
    expect(offline.status).toBe('queued');
    expect(offline.localSaved).toBe(true);
    expect(await client.pending()).toBe(1);

    server.offline = false;
    const flushed = await client.flush();
    expect(flushed.offline).toBe(false);
    expect(flushed.uploaded).toHaveLength(1);
    expect(flushed.uploaded[0].snapshotId).toContain('snap_');
    expect(await client.pending()).toBe(0);
    expect(server.worlds.get('w1')!.revision).toBe(1);
  });

  it('chains multiple offline saves instead of sending them all against the same stale head', async () => {
    const server = new FakeProgressServer();
    const { client } = makeClient(server);
    server.offline = true;

    const first = await client.save('w1', snapshot(1, '离线第一步'), { requestId: 'off-1' });
    const second = await client.save('w1', snapshot(2, '离线第二步'), { requestId: 'off-2' });
    expect(first.status).toBe('queued');
    expect(second.status).toBe('queued');
    if (second.status !== 'queued') throw new Error('expected queued');
    expect(second.reason).toBe('queued_behind');
    expect(await client.pending()).toBe(2);
    expect(server.worlds.get('w1')).toBeUndefined();

    server.offline = false;
    const flushed = await client.flush();
    expect(flushed.uploaded).toHaveLength(2);
    expect(flushed.conflicts).toHaveLength(0);
    expect(await client.pending()).toBe(0);
    expect(server.worlds.get('w1')!.revision).toBe(2);
    expect(server.worlds.get('w1')!.nodes.size).toBe(2);
    const recovered = await client.pullLatest('w1');
    expect(recovered.snapshot?.payload).toEqual(snapshot(2, '离线第二步'));
    expect(recovered.snapshot?.parentSnapshotIds).toEqual([flushed.uploaded[0].snapshotId]);
  });

  it('chains a queued save behind a possibly-applied upload without resending a stale body', async () => {
    const server = new FakeProgressServer();
    const { client } = makeClient(server);
    server.loseNextUploadResponse = true;

    const first = await client.save('w1', snapshot(1, '响应丢失'), { requestId: 'lost-then-queued' });
    expect(first.status).toBe('queued');
    expect(server.worlds.get('w1')!.revision).toBe(1);

    const second = await client.save('w1', snapshot(2, '后续离线'), { requestId: 'behind-lost' });
    expect(second.status).toBe('queued');
    if (second.status !== 'queued') throw new Error('expected queued');
    expect(second.reason).toBe('queued_behind');
    // The second body was never sent.
    expect(server.calls.filter((call) => call.method === 'POST')).toHaveLength(1);

    const flushed = await client.flush();
    expect(flushed.uploaded).toHaveLength(2);
    expect(flushed.uploaded[0].idempotent).toBe(true);
    expect(server.worlds.get('w1')!.revision).toBe(2);
    expect(flushed.uploaded[1].headSnapshotId).toBe(flushed.uploaded[1].snapshotId);
    expect((await client.pullLatest('w1')).snapshot?.payload).toEqual(snapshot(2, '后续离线'));
  });

  it('rebases dependent offline saves after an explicit fork choice', async () => {
    const server = new FakeProgressServer();
    const deviceA = makeClient(server);
    const root = await deviceA.client.save('w1', snapshot(1, 'root'), { requestId: 'a1' });
    if (root.status !== 'synced') throw new Error('root failed');

    const deviceB = makeClient(server);
    await deviceB.client.head('w1');
    server.offline = true;
    const b1 = await deviceB.client.save('w1', snapshot(2, 'B1'), { requestId: 'b1' });
    const b2 = await deviceB.client.save('w1', snapshot(3, 'B2'), { requestId: 'b2' });
    expect(b1.status).toBe('queued');
    expect(b2.status).toBe('queued');

    server.offline = false;
    const advanced = await deviceA.client.save('w1', snapshot(2, 'A2'), { requestId: 'a2' });
    if (advanced.status !== 'synced') throw new Error('advance failed');

    const flushed = await deviceB.client.flush();
    expect(flushed.conflicts).toHaveLength(1);
    expect(flushed.conflicts[0].requestId).toBe('b1');
    expect(flushed.failures.some((failure) => failure.code === 'dependency_missing')).toBe(true);
    expect(flushed.remaining).toBe(2);

    const resolved = await deviceB.client.resolveQueuedConflict('b1', 'keep-local-fork');
    expect(resolved.status).toBe('local-fork');
    const secondFlush = await deviceB.client.flush();
    expect(secondFlush.uploaded).toHaveLength(1);
    expect(secondFlush.uploaded[0].headSnapshotId).toBe(secondFlush.uploaded[0].snapshotId);
    expect(await deviceB.client.pending()).toBe(0);

    const graph = await deviceB.client.graph('w1');
    expect(graph.headSnapshotId).toBe(secondFlush.uploaded[0].snapshotId);
    expect(graph.branches).toEqual([secondFlush.uploaded[0].snapshotId, advanced.upload.snapshotId].sort());
    expect((await deviceB.client.read('w1', advanced.upload.snapshotId)).payload).toEqual(snapshot(2, 'A2'));
    expect((await deviceB.client.pullLatest('w1')).snapshot?.payload).toEqual(snapshot(3, 'B2'));
  });

  it('retries a lost response idempotently instead of creating a second revision', async () => {
    const server = new FakeProgressServer();
    const { client } = makeClient(server);
    server.loseNextUploadResponse = true;

    const first = await client.save('w1', snapshot(1), { requestId: 'lost-response' });
    expect(first.status).toBe('queued');
    expect(server.worlds.get('w1')!.revision).toBe(1);

    const flushed = await client.flush();
    expect(flushed.uploaded).toHaveLength(1);
    expect(flushed.uploaded[0].idempotent).toBe(true);
    expect(server.worlds.get('w1')!.revision).toBe(1);
    expect(server.worlds.get('w1')!.nodes.size).toBe(1);
  });

  it('keeps both branches when an offline local save forks from an old head', async () => {
    const server = new FakeProgressServer();
    const deviceA = makeClient(server);
    const root = await deviceA.client.save('w1', snapshot(1), { requestId: 'a1' });
    if (root.status !== 'synced') throw new Error('root failed');
    const branchA = await deviceA.client.save('w1', snapshot(2, 'A线'), { requestId: 'a2' });
    if (branchA.status !== 'synced') throw new Error('branch A failed');

    const deviceB = makeClient(server);
    const stale = await deviceB.client.save('w1', snapshot(2, 'B线'), {
      requestId: 'b1',
      expectedHead: root.upload.snapshotId,
      expectedRevision: root.upload.revision,
    });
    if (stale.status !== 'conflict') throw new Error('expected conflict');

    const resolved = await deviceB.client.resolveConflict(stale.conflict, 'keep-local-fork');
    expect(resolved.status).toBe('local-fork');
    expect(resolved.head.headSnapshotId).toBe(resolved.upload!.snapshotId);
    expect(resolved.snapshot?.payload).toEqual(snapshot(2, 'B线'));

    const graph = await deviceB.client.graph('w1');
    expect(new Set(graph.branches)).toEqual(new Set([branchA.upload.snapshotId, resolved.upload!.snapshotId]));
    expect(graph.nodes).toHaveLength(3);
    expect((await deviceB.client.read('w1', branchA.upload.snapshotId)).payload).toEqual(snapshot(2, 'A线'));

    // A is not merged into B: both branches retain their own parent.
    const bNode = graph.nodes.find((node) => node.snapshotId === resolved.upload!.snapshotId)!;
    expect(bNode.parentSnapshotIds).toEqual([root.upload.snapshotId]);

    const comparison = compareLineage(
      branchA.upload.snapshotId,
      resolved.upload!.snapshotId,
      graph.nodes,
    );
    expect(comparison.commonAncestor).toBe(root.upload.snapshotId);
    expect(comparison.diverged).toBe(true);
  });

  it('selects a branch without deleting the other one, then another device recovers it', async () => {
    const server = new FakeProgressServer();
    const deviceA = makeClient(server);
    const root = await deviceA.client.save('w1', snapshot(1), { requestId: 'a1' });
    if (root.status !== 'synced') throw new Error('root failed');
    const branchA = await deviceA.client.save('w1', snapshot(2, 'A线'), { requestId: 'a2' });
    if (branchA.status !== 'synced') throw new Error('branch A failed');
    const branchB = await deviceA.client.fork('w1', snapshot(2, 'B线'), {
      baseSnapshotId: root.upload.snapshotId,
      expectedHead: branchA.upload.headSnapshotId,
      expectedRevision: branchA.upload.revision,
      requestId: 'b-fork',
    });

    const chosen = await deviceA.client.selectBranch('w1', branchB.snapshotId, {
      expectedHead: branchB.headSnapshotId,
      expectedRevision: branchB.revision,
      requestId: 'choose-b',
    });
    expect(chosen.headSnapshotId).toBe(branchB.snapshotId);

    const graph = await deviceA.client.graph('w1');
    expect(graph.branches).toContain(branchA.upload.snapshotId);
    expect(graph.branches).toContain(branchB.snapshotId);

    const deviceB = makeClient(server);
    const recovered = await deviceB.client.pullLatest('w1');
    expect(recovered.localSaved).toBe(true);
    expect(recovered.snapshot?.payload).toEqual(snapshot(2, 'B线'));
    expect(deviceB.localStore.values.get('w1')).toEqual(snapshot(2, 'B线'));

    await deviceA.client.selectBranch('w1', branchA.upload.snapshotId, {
      expectedHead: branchB.snapshotId,
      expectedRevision: branchB.revision + 1,
      requestId: 'choose-a',
    });
    const recoveredA = await deviceB.client.pullLatest('w1');
    expect(recoveredA.snapshot?.payload).toEqual(snapshot(2, 'A线'));
  });

  it('restores progress across two devices in both directions', async () => {
    const server = new FakeProgressServer();
    const deviceA = makeClient(server);
    const a1 = await deviceA.client.save('w1', snapshot(1, 'A1'), { requestId: 'a1' });
    if (a1.status !== 'synced') throw new Error('a1 failed');
    const a2 = await deviceA.client.save('w1', snapshot(2, 'A2'), { requestId: 'a2' });
    if (a2.status !== 'synced') throw new Error('a2 failed');

    const deviceB = makeClient(server);
    const pulledA = await deviceB.client.pullLatest('w1');
    expect(pulledA.snapshot?.payload).toEqual(snapshot(2, 'A2'));

    const b1 = await deviceB.client.save('w1', snapshot(3, 'B1'), { requestId: 'b1' });
    expect(b1.status).toBe('synced');

    const pulledB = await deviceA.client.pullLatest('w1');
    expect(pulledB.snapshot?.payload).toEqual(snapshot(3, 'B1'));
    expect(deviceA.localStore.values.get('w1')).toEqual(snapshot(3, 'B1'));
  });

  it('resolves a queued conflict in either direction without auto-merging', async () => {
    const server = new FakeProgressServer();
    const deviceA = makeClient(server);
    const root = await deviceA.client.save('w1', snapshot(1), { requestId: 'a1' });
    if (root.status !== 'synced') throw new Error('root failed');

    // B knows root, A advances while B is offline.
    const deviceB = makeClient(server);
    await deviceB.client.head('w1');
    const advanced = await deviceA.client.save('w1', snapshot(2, 'A2'), { requestId: 'a2' });
    if (advanced.status !== 'synced') throw new Error('advance failed');
    server.offline = true;
    const queued = await deviceB.client.save('w1', snapshot(2, 'B2'), { requestId: 'b2' });
    expect(queued.status).toBe('queued');

    server.offline = false;
    const flushed = await deviceB.client.flush();
    expect(flushed.conflicts).toHaveLength(1);
    expect(flushed.remaining).toBe(1);

    const local = await deviceB.client.resolveQueuedConflict('b2', 'keep-local-fork');
    expect(local.status).toBe('local-fork');
    expect(local.snapshot?.payload).toEqual(snapshot(2, 'B2'));
    expect(await deviceB.client.pending()).toBe(0);
    expect((await deviceB.client.read('w1', advanced.upload.snapshotId)).payload).toEqual(snapshot(2, 'A2'));
  });

  it('can keep the remote branch instead of the offline local save', async () => {
    const server = new FakeProgressServer();
    const deviceA = makeClient(server);
    const root = await deviceA.client.save('w1', snapshot(1), { requestId: 'a1' });
    if (root.status !== 'synced') throw new Error('root failed');
    const deviceB = makeClient(server);
    await deviceB.client.head('w1');
    const advanced = await deviceA.client.save('w1', snapshot(2, 'A2'), { requestId: 'a2' });
    if (advanced.status !== 'synced') throw new Error('advance failed');

    server.offline = true;
    await deviceB.client.save('w1', snapshot(2, 'B2'), { requestId: 'b2' });
    server.offline = false;
    await deviceB.client.flush();
    const remote = await deviceB.client.resolveQueuedConflict('b2', 'keep-remote');
    expect(remote.status).toBe('remote');
    expect(remote.snapshot?.payload).toEqual(snapshot(2, 'A2'));
    expect(deviceB.localStore.values.get('w1')).toEqual(snapshot(2, 'A2'));
    expect(await deviceB.client.pending()).toBe(0);
  });

  it('save(localOnly) never calls the network and queue survives web storage', async () => {
    const server = new FakeProgressServer();
    const storage = new Map<string, string>();
    const queue = createWebStorageQueueStore('queue-key', {
      getItem: (key) => storage.get(key) ?? null,
      setItem: (key, value) => storage.set(key, value),
    });
    const { client } = makeClient(server, new MemoryLocalStore(), queue);
    server.offline = true;
    const localOnly = await client.save('w1', snapshot(1), { requestId: 'local-only', localOnly: true });
    expect(localOnly.status).toBe('local-only');
    expect(server.calls).toHaveLength(0);
    expect(await client.pending()).toBe(0);

    const queued = await client.save('w1', snapshot(2), { requestId: 'queued-2' });
    expect(queued.status).toBe('queued');
    expect(storage.has('queue-key')).toBe(true);

    const restored = makeClient(server, new MemoryLocalStore(), queue);
    expect(await restored.client.pending()).toBe(1);
    server.offline = false;
    const flushed = await restored.client.flush();
    expect(flushed.uploaded).toHaveLength(1);
  });

  it('keeps a 5xx upload queued and reports the server error as retryable offline state', async () => {
    const server = new FakeProgressServer();
    const { client } = makeClient(server);
    server.failNextWith500 = true;
    const outcome = await client.save('w1', snapshot(1), { requestId: 'five-hundred' });
    expect(outcome.status).toBe('queued');
    if (outcome.status !== 'queued') throw new Error('expected queue');
    expect(outcome.reason).toBe('server_error');
    expect(await client.pending()).toBe(1);
  });
});

describe('createProductSync', () => {
  class ProductStore {
    values = new Map<string, { snapshot: unknown }>();
    saves = 0;
    async load(worldId: string) {
      return this.values.get(worldId) ?? null;
    }
    async save(worldId: string, snapshot: unknown) {
      this.saves += 1;
      this.values.set(worldId, { snapshot: structuredClone(snapshot) });
      return { revision: this.saves };
    }
  }

  class MemoryStorage {
    values = new Map<string, string>();
    getItem(key: string) {
      return this.values.get(key) ?? null;
    }
    setItem(key: string, value: string) {
      this.values.set(key, value);
    }
  }

  it('plays and saves locally with no service configured (explicit local writer)', async () => {
    const store = new ProductStore();
    const sync = createProductSync<unknown>({ store, worldId: 'w1', writeLocal: true });
    const saved = await sync.save(snapshot(1));
    expect(saved.localSaved).toBe(true);
    expect(saved.note).toContain('nothing to upload');
    const restored = await sync.restore();
    expect(restored.source).toBe('local');
    expect(restored.snapshot).toEqual(snapshot(1));
    expect(await sync.pending()).toBe(0);
    expect(await sync.flush()).toMatchObject({ uploaded: 0, remaining: 0 });
  });

  it('by default never writes the store the product session owns', async () => {
    // 06's store checks a revision. A second writer moves the revision behind
    // the session, and the session's next save fails as a conflict before any
    // model call. The adapter must upload only.
    const values = new Map<string, { snapshot: unknown; revision: number }>();
    const revisionChecked = {
      values,
      async load(worldId: string) {
        return values.get(worldId) ?? null;
      },
      async save(worldId: string, payload: unknown, options?: { expectedRevision?: number }) {
        const current = values.get(worldId);
        const expected = options?.expectedRevision;
        if (expected !== undefined && current && current.revision !== expected) {
          throw new Error('revision_conflict');
        }
        const next = { snapshot: structuredClone(payload), revision: (current?.revision ?? 0) + 1 };
        values.set(worldId, next);
        return { revision: next.revision };
      },
    };
    const server = new FakeProgressServer();
    const sync = createProductSync<unknown>({
      store: revisionChecked,
      worldId: 'w1',
      baseUrl: 'http://sync.test',
      fetchImpl: server.fetch,
      retry: { attempts: 1, baseDelayMs: 0 },
      sleep: async () => undefined,
    });
    // The session saves first, as 06's does.
    await revisionChecked.save('w1', snapshot(1), { expectedRevision: 0 });
    const saved = await sync.save(snapshot(1), { requestId: 'session-owned' });
    expect(saved.localSaved).toBe(false);
    expect(saved.outcome?.status).toBe('synced');
    expect(values.get('w1')?.revision).toBe(1);
    // The session's next save still checks against the revision it owns.
    await expect(revisionChecked.save('w1', snapshot(2), { expectedRevision: 1 })).resolves.toBeTruthy();
  });

  it('wires the product store and browser storage into the real client', async () => {
    const server = new FakeProgressServer();
    const store = new ProductStore();
    const storage = new MemoryStorage();
    const sync = createProductSync<unknown>({
      store,
      worldId: 'w1',
      baseUrl: 'http://sync.test',
      storage,
      fetchImpl: server.fetch,
      retry: { attempts: 1, baseDelayMs: 0 },
      sleep: async () => undefined,
      now: () => 1_700_000_000_000,
    });

    // 06's page saves through its own store, then asks sync to upload.
    await store.save('w1', snapshot(1));
    const first = await sync.push(snapshot(1), { requestId: 'product-1' });
    expect(first.localSaved).toBe(false);
    expect(first.outcome?.status).toBe('synced');
    expect(store.saves).toBe(1);
    expect(store.values.get('w1')?.snapshot).toEqual(snapshot(1));
    expect(storage.getItem('jity.progress-sync.heads.v1')).toContain('headSnapshotId');

    // New page, same durable store and storage: restore reads local, and the
    // head store keeps the CAS values even though the client is fresh.
    const reloaded = createProductSync<unknown>({
      store,
      worldId: 'w1',
      baseUrl: 'http://sync.test',
      storage,
      fetchImpl: server.fetch,
      retry: { attempts: 1, baseDelayMs: 0 },
      sleep: async () => undefined,
      now: () => 1_700_000_000_000,
    });
    const restored = await reloaded.restore();
    expect(restored.source).toBe('local');
    expect(restored.snapshot).toEqual(snapshot(1));

    await store.save('w1', snapshot(2));
    server.offline = true;
    const offline = await reloaded.push(snapshot(2), { requestId: 'product-2' });
    expect(offline.outcome?.status).toBe('queued');
    expect(await reloaded.pending()).toBe(1);
    expect(storage.getItem('jity.progress-sync.queue.v1')).toContain('product-2');

    server.offline = false;
    const flushed = await reloaded.flush();
    expect(flushed.uploaded).toBe(1);
    expect(flushed.remaining).toBe(0);
    expect(server.worlds.get('w1')!.revision).toBe(2);

    const other = createProductSync<unknown>({
      store: new ProductStore(),
      worldId: 'w1',
      baseUrl: 'http://sync.test',
      storage: new MemoryStorage(),
      fetchImpl: server.fetch,
      retry: { attempts: 1, baseDelayMs: 0 },
      sleep: async () => undefined,
    });
    const remote = await other.restore();
    expect(remote.source).toBe('remote');
    expect(remote.snapshot).toEqual(snapshot(2));
  });

  it('returns a conflict for the player to decide and never overwrites silently', async () => {
    const server = new FakeProgressServer();
    const storageA = new MemoryStorage();
    const a = createProductSync<unknown>({
      store: new ProductStore(),
      worldId: 'w1',
      baseUrl: 'http://sync.test',
      storage: storageA,
      fetchImpl: server.fetch,
      retry: { attempts: 1, baseDelayMs: 0 },
      sleep: async () => undefined,
      now: () => 1_700_000_000_000,
    });
    const storageB = new MemoryStorage();
    const b = createProductSync<unknown>({
      store: new ProductStore(),
      worldId: 'w1',
      baseUrl: 'http://sync.test',
      storage: storageB,
      fetchImpl: server.fetch,
      retry: { attempts: 1, baseDelayMs: 0 },
      sleep: async () => undefined,
      now: () => 1_700_000_000_000,
    });
    await a.save(snapshot(1), { requestId: 'conf-1' });
    // B joins after A's save: pull the head first, then play on from it.
    expect((await b.restore()).source).toBe('remote');
    expect((await b.save(snapshot(2), { requestId: 'conf-b' })).outcome?.status).toBe('synced');

    const clashing = await a.save(snapshot(2, 'A的另一份'), { requestId: 'conf-a' });
    expect(clashing.outcome?.status).toBe('conflict');
    if (clashing.outcome?.status !== 'conflict') throw new Error('expected conflict');

    const kept = await a.choose('keep-local-fork', clashing.outcome.conflict);
    expect(kept.status).toBe('local-fork');
    const graph = await a.client.graph('w1');
    expect(graph.nodes).toHaveLength(3);
    expect(graph.branches.length).toBe(2);
    expect(graph.branches).toContain(kept.upload!.snapshotId);
    expect((await a.read(kept.upload!.snapshotId)).payload).toEqual(snapshot(2, 'A的另一份'));
  });

  it('push uploads a save the caller already stored, without a second local write', async () => {
    const server = new FakeProgressServer();
    const store = new ProductStore();
    const sync = createProductSync<unknown>({
      store,
      worldId: 'w1',
      baseUrl: 'http://sync.test',
      storage: new MemoryStorage(),
      fetchImpl: server.fetch,
      retry: { attempts: 1, baseDelayMs: 0 },
      sleep: async () => undefined,
      now: () => 1_700_000_000_000,
    });
    // The page saved through 06's repository first (one local revision).
    await store.save('w1', snapshot(1));
    expect(store.saves).toBe(1);

    const pushed = await sync.push(snapshot(1), { requestId: 'push-1' });
    expect(pushed.outcome?.status).toBe('synced');
    expect(store.saves).toBe(1);
    expect(server.worlds.get('w1')!.revision).toBe(1);
  });

  it('reports in-sync, remote-ahead, local-ahead and diverged before writing anything', async () => {
    const server = new FakeProgressServer();
    const storeA = new ProductStore();
    const storageA = new MemoryStorage();
    const make = (store: ProductStore, storage: MemoryStorage) => createProductSync<unknown>({
      store,
      worldId: 'w1',
      baseUrl: 'http://sync.test',
      storage,
      fetchImpl: server.fetch,
      retry: { attempts: 1, baseDelayMs: 0 },
      sleep: async () => undefined,
      now: () => 1_700_000_000_000,
    });

    const a = make(storeA, storageA);
    expect((await a.status()).relation).toBe('unknown');
    await storeA.save('w1', snapshot(1));
    await a.push(snapshot(1), { requestId: 'st-1' });
    expect((await a.status()).relation).toBe('in-sync');

    // Another device advances the remote.
    const storeB = new ProductStore();
    const b = make(storeB, new MemoryStorage());
    expect((await b.restore()).source).toBe('remote');
    await b.push(snapshot(2), { requestId: 'st-2' });
    expect((await a.status()).relation).toBe('remote-ahead');

    // A third device forks from the root while A is still on revision 1.
    const forked = await b.client.fork('w1', snapshot(9, '分叉'), {
      baseSnapshotId: server.worlds.get('w1')!.headSnapshotId!,
      expectedHead: server.worlds.get('w1')!.headSnapshotId!,
      expectedRevision: server.worlds.get('w1')!.revision,
      requestId: 'st-fork',
    });
    expect(forked.snapshotId).toBeTruthy();
    // B is now ahead of the active head, which is still A's base + 1: A is
    // behind but the graph has two leaves.
    expect((await a.status()).relation).toBe('remote-ahead');

    // A local save made while B moved on, then restored from an old base,
    // reports diverged instead of silently overwriting.
    const storeC = new ProductStore();
    const c = make(storeC, new MemoryStorage());
    await storeC.save('w1', snapshot(5, 'C的副本'));
    await c.push(snapshot(5, 'C的副本'), { requestId: 'st-c' });
    const cStatus = await c.status();
    expect(cStatus.relation).toBe('diverged');
    // Nothing is written by status(); the page only learns it must ask.
    expect(Array.isArray(cStatus.branches)).toBe(true);
  });

  it('flush returns the conflicts themselves so the page can ask the player', async () => {
    const server = new FakeProgressServer();
    const a = createProductSync<unknown>({
      store: new ProductStore(),
      worldId: 'w1',
      baseUrl: 'http://sync.test',
      storage: new MemoryStorage(),
      fetchImpl: server.fetch,
      retry: { attempts: 1, baseDelayMs: 0 },
      sleep: async () => undefined,
      now: () => 1_700_000_000_000,
    });
    await a.save(snapshot(1), { requestId: 'fl-1' });
    // Another device moves the head while A is offline with a queued save.
    server.offline = true;
    const queued = await a.save(snapshot(2, 'A离线'), { requestId: 'fl-2' });
    expect(queued.outcome?.status).toBe('queued');
    const b = createProductSync<unknown>({
      store: new ProductStore(),
      worldId: 'w1',
      baseUrl: 'http://sync.test',
      storage: new MemoryStorage(),
      fetchImpl: server.fetch,
      retry: { attempts: 1, baseDelayMs: 0 },
      sleep: async () => undefined,
      now: () => 1_700_000_000_000,
    });
    server.offline = false;
    // B pulls A's first save? No: B must build on the same head A saw.
    expect((await b.restore()).snapshot).toEqual(snapshot(1));
    await b.save(snapshot(3, 'B在线'), { requestId: 'fl-b' });

    const flushed = await a.flush();
    expect(flushed.uploaded).toBe(0);
    expect(flushed.conflicts).toBe(1);
    expect(flushed.conflictList).toHaveLength(1);
    const conflict = flushed.conflictList[0];
    expect(conflict.code).toBeTruthy();
    expect(conflict.remote.headSnapshotId).toBeTruthy();
    // Both copies are preserved until the player chooses.
    const kept = await a.choose('keep-local-fork', conflict);
    expect(kept.status).toBe('local-fork');
    const graph = await a.client.graph('w1');
    expect((await a.read(kept.upload!.snapshotId)).payload).toEqual(snapshot(2, 'A离线'));
    expect(graph.branches.length).toBe(2);
  });

  it('a head store survives malformed storage without breaking saves', async () => {
    const storage = new MemoryStorage();
    storage.setItem('jity.progress-sync.heads.v1', '{not json');
    const heads = createWebStorageHeadStore(storage);
    expect(await heads.load('w1')).toBeNull();
    await heads.save('w1', { worldId: 'w1', headSnapshotId: 'snap_1', revision: 3 });
    expect((await heads.load('w1'))?.revision).toBe(3);
  });
});

describe('compareLineage', () => {
  const nodes = [
    { snapshotId: 'root', parentSnapshotIds: [] },
    { snapshotId: 'left', parentSnapshotIds: ['root'] },
    { snapshotId: 'left2', parentSnapshotIds: ['left'] },
    { snapshotId: 'right', parentSnapshotIds: ['root'] },
  ];

  it('finds the shared ancestor and both branch suffixes', () => {
    const comparison = compareLineage('left2', 'right', nodes);
    expect(comparison.commonAncestor).toBe('root');
    expect(comparison.sharedHistory).toEqual(['root']);
    expect(comparison.leftOnly).toEqual(['left', 'left2']);
    expect(comparison.rightOnly).toEqual(['right']);
    expect(comparison.diverged).toBe(true);
    expect(comparison.leftIsAncestorOfRight).toBe(false);
  });

  it('marks a true ancestor relationship', () => {
    const comparison = compareLineage('root', 'left2', nodes);
    expect(comparison.leftIsAncestorOfRight).toBe(true);
    expect(comparison.rightIsAncestorOfLeft).toBe(false);
    expect(comparison.diverged).toBe(false);
    expect(comparison.leftOnly).toEqual([]);
    expect(comparison.rightOnly).toEqual(['left', 'left2']);
  });

  it('treats the same snapshot as identical', () => {
    const comparison = compareLineage('left', 'left', nodes);
    expect(comparison.same).toBe(true);
    expect(comparison.diverged).toBe(false);
    expect(comparison.commonAncestor).toBe('left');
    expect(comparison.leftOnly).toEqual([]);
    expect(comparison.rightOnly).toEqual([]);
  });

  it('does not use insertion order or timestamps to pick an ancestor', () => {
    const reversed = [...nodes].reverse();
    expect(compareLineage('left2', 'right', reversed)).toEqual(compareLineage('left2', 'right', nodes));
  });

  it('throws on unknown snapshots', () => {
    expect(() => compareLineage('missing', 'root', nodes)).toThrow(ProgressSyncError);
  });
});
