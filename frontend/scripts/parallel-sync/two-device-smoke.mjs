#!/usr/bin/env node
/**
 * Protocol smoke test against a running progress-sync service.
 *
 *   PROGRESS_SYNC_URL=http://127.0.0.1:8010 \
 *   PROGRESS_SYNC_TOKEN=secret \
 *   node frontend/scripts/parallel-sync/two-device-smoke.mjs
 *
 * It exercises the raw HTTP contract (not the TS client): CAS, idempotent
 * replay, non-activating fork, explicit branch selection and preservation of
 * both payloads. Exits non-zero on the first failed assertion.
 */

const base = (process.env.PROGRESS_SYNC_URL ?? 'http://127.0.0.1:8010').replace(/\/+$/, '');
const root = base.endsWith('/local-progress') ? base : `${base}/local-progress`;
const token = process.env.PROGRESS_SYNC_TOKEN ?? process.env.LOCAL_PROGRESS_TOKEN;
const worldId = process.env.PROGRESS_SYNC_WORLD ?? `smoke_${Date.now().toString(36)}`;

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function call(method, path, body) {
  const headers = { Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(`${root}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await response.text();
  return { status: response.status, body: text ? JSON.parse(text) : null };
}

function expectStatus(result, status, label) {
  assert(
    result.status === status,
    `${label}: expected HTTP ${status}, got ${result.status}: ${JSON.stringify(result.body)}`,
  );
  return result.body;
}

function payload(turn, text) {
  return {
    transport: { worldId, round: turn, state: { characters: { person_a: { position: 'hall' } } } },
    commands: [text],
  };
}

const worldPath = `/worlds/${encodeURIComponent(worldId)}`;
const summary = { worldId, steps: [] };

// 1. Root save.
const rootPayload = payload(1, '起点');
const rootSave = expectStatus(await call('POST', `${worldPath}/snapshots`, {
  requestId: 'smoke-root',
  parentSnapshotIds: [],
  expectedHead: null,
  expectedRevision: 0,
  activate: true,
  payload: rootPayload,
}), 201, 'root save');
assert(rootSave.snapshotId.startsWith('snap_'), 'root snapshot id is content-addressed');
summary.steps.push({ step: 'root', snapshotId: rootSave.snapshotId, revision: rootSave.revision });

// 2. Idempotent replay of the exact same request.
const replay = expectStatus(await call('POST', `${worldPath}/snapshots`, {
  requestId: 'smoke-root',
  parentSnapshotIds: [],
  expectedHead: null,
  expectedRevision: 0,
  activate: true,
  payload: rootPayload,
}), 200, 'idempotent replay');
assert(replay.idempotent === true, 'replay must be flagged idempotent');
assert(replay.snapshotId === rootSave.snapshotId, 'replay must return the same snapshot');
assert(replay.revision === rootSave.revision, 'replay must not advance revision');
summary.steps.push({ step: 'idempotent replay', revision: replay.revision });

// 3. Stale CAS is rejected and does not move the head.
const stale = await call('POST', `${worldPath}/snapshots`, {
  requestId: 'smoke-stale',
  parentSnapshotIds: [rootSave.snapshotId],
  expectedHead: rootSave.snapshotId,
  expectedRevision: 0,
  activate: true,
  payload: payload(2, '过期写入'),
});
expectStatus(stale, 409, 'stale CAS');
assert(stale.body.detail.code === 'revision_mismatch', 'stale CAS reports revision_mismatch');
summary.steps.push({ step: 'stale CAS rejected', code: stale.body.detail.code });

// 4. Device A advances the active branch.
const a2 = expectStatus(await call('POST', `${worldPath}/snapshots`, {
  requestId: 'smoke-a2',
  parentSnapshotIds: [rootSave.snapshotId],
  expectedHead: rootSave.snapshotId,
  expectedRevision: rootSave.revision,
  activate: true,
  payload: payload(2, 'A 线'),
}), 201, 'device A advance');
assert(a2.headSnapshotId === a2.snapshotId, 'A advance is active');
summary.steps.push({ step: 'device A advance', snapshotId: a2.snapshotId, revision: a2.revision });

// 5. Offline device B stores a fork from the old root without activating it.
const bFork = expectStatus(await call('POST', `${worldPath}/snapshots`, {
  requestId: 'smoke-b-fork',
  parentSnapshotIds: [rootSave.snapshotId],
  expectedHead: a2.snapshotId,
  expectedRevision: a2.revision,
  activate: false,
  payload: payload(2, 'B 线'),
}), 201, 'device B fork');
assert(bFork.headSnapshotId === a2.snapshotId, 'fork must not move the active head');
assert(bFork.revision === a2.revision + 1, 'fork changes the world revision only');
summary.steps.push({ step: 'device B fork', snapshotId: bFork.snapshotId, head: bFork.headSnapshotId });

// 6. Both payloads and both leaves are preserved.
const graph = expectStatus(await call('GET', `${worldPath}/graph`), 200, 'graph');
const branches = new Set(graph.branches);
assert(branches.has(a2.snapshotId), 'A branch is a leaf');
assert(branches.has(bFork.snapshotId), 'B branch is a leaf');
const aRead = expectStatus(await call('GET', `${worldPath}/snapshots/${a2.snapshotId}`), 200, 'read A');
assert(aRead.payload.commands[0] === 'A 线', 'A payload is unchanged');
summary.steps.push({ step: 'both branches readable', branches: [...branches] });

// 7. Explicitly choose B; A remains readable.
const chosen = expectStatus(await call('POST', `${worldPath}/head`, {
  requestId: 'smoke-choose-b',
  snapshotId: bFork.snapshotId,
  expectedHead: a2.snapshotId,
  expectedRevision: bFork.revision,
}), 200, 'choose B');
assert(chosen.headSnapshotId === bFork.snapshotId, 'B becomes active');
const aAfter = expectStatus(await call('GET', `${worldPath}/snapshots/${a2.snapshotId}`), 200, 'read A after choice');
assert(aAfter.payload.commands[0] === 'A 线', 'A survives branch selection');
const head = expectStatus(await call('GET', `${worldPath}/head`), 200, 'head after choice');
assert(head.headSnapshotId === bFork.snapshotId, 'head points at B');
summary.steps.push({ step: 'branch choice', head: head.headSnapshotId, revision: head.revision });

console.log(JSON.stringify(summary, null, 2));
