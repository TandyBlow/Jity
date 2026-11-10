// Local GPU / real-browser queue bookkeeping for 09.
//
// Every lane (including 06 and 08) drops a request file into
// `results/product/browser-requests/<lane>-<id>.json`. This script only keeps
// the queue honest: it never runs inference itself, never touches another lane's
// files, and never silently drops a request.
//
//   node scripts/product-acceptance/browser-queue.mjs --sync
//   node scripts/product-acceptance/browser-queue.mjs --list
//   node scripts/product-acceptance/browser-queue.mjs --next
//   node scripts/product-acceptance/browser-queue.mjs --claim <itemId> --pid <pid>
//   node scripts/product-acceptance/browser-queue.mjs --finish <itemId> \
//        --status completed|failed --evidence <path> [--note "..."]
//
// Priority (higher first), per tasks/product-09-acceptance.md:
//   P0 product-blocking / cancel / restore / save-service
//   P1 ten/twenty-turn product regression
//   P2 targeted quality fix for an existing candidate
//   P3 new candidate first look
// Within the same priority the earlier `requestedAt` goes first and nothing is
// starved: a claimed item that never finishes is reported by --stale.

import { existsSync, mkdirSync, readFileSync, readdirSync, renameSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../../../../..');
const queuePath = resolve(root, 'results/product/browser-queue.json');
const requestsDir = resolve(root, 'results/product/browser-requests');
const PRIORITY = { p0: 0, p1: 1, p2: 2, p3: 3 };

function flag(name, fallback = null) {
  const index = process.argv.indexOf(name);
  return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
}
const has = (name) => process.argv.includes(name);

function load() {
  if (!existsSync(queuePath)) {
    return {
      kind: 'browser-queue',
      owner: '09-ui',
      updatedAt: new Date().toISOString(),
      items: [],
      orphanRequests: [],
      note: '09-ui owns this file; other lanes only write browser-requests/*.json',
    };
  }
  return JSON.parse(readFileSync(queuePath, 'utf8'));
}

function save(queue) {
  queue.updatedAt = new Date().toISOString();
  mkdirSync(dirname(queuePath), { recursive: true });
  const tmp = `${queuePath}.tmp-${process.pid}`;
  writeFileSync(tmp, JSON.stringify(queue, null, 2));
  renameSync(tmp, queuePath);
}

function sync(queue) {
  if (!existsSync(requestsDir)) return queue;
  const seen = new Set(queue.items.map((item) => item.itemId));
  for (const file of readdirSync(requestsDir).filter((name) => name.endsWith('.json')).sort()) {
    const full = join(requestsDir, file);
    let request;
    try {
      request = JSON.parse(readFileSync(full, 'utf8'));
    } catch (error) {
      queue.orphanRequests.push({ file, error: `unreadable: ${String(error).slice(0, 200)}`, at: new Date().toISOString() });
      continue;
    }
    const lane = request.lane ?? request.requestedBy ?? file.split('-')[0];
    const id = request.id ?? file.replace(/\.json$/, '');
    const itemId = `${lane}:${id}`;
    if (seen.has(itemId)) continue;
    const missing = ['purpose', 'requestedAt'].filter((key) => !request[key]);
    if (!request.purpose) {
      queue.orphanRequests.push({ file, itemId, error: 'no purpose', at: new Date().toISOString() });
      continue;
    }
    queue.items.push({
      itemId,
      lane,
      file,
      purpose: request.purpose,
      priority: (request.priority ?? 'p2').toLowerCase(),
      model: request.model ?? null,
      modelSha256: request.modelSha256 ?? null,
      productCommit: request.productCommit ?? null,
      command: request.command ?? null,
      inputs: request.inputs ?? null,
      questions: request.questions ?? null,
      status: 'requested',
      requestedAt: request.requestedAt,
      syncedAt: new Date().toISOString(),
      missingFields: missing,
      claims: [],
      runs: [],
    });
    seen.add(itemId);
  }
  return queue;
}

function ordered(queue) {
  return [...queue.items]
    .filter((item) => item.status === 'requested' || item.status === 'failed' || item.status === 'running')
    .sort((a, b) => {
      const pa = PRIORITY[a.priority] ?? 9;
      const pb = PRIORITY[b.priority] ?? 9;
      if (pa !== pb) return pa - pb;
      if (a.status === 'running' && b.status !== 'running') return -1;
      if (b.status === 'running' && a.status !== 'running') return 1;
      return String(a.requestedAt).localeCompare(String(b.requestedAt));
    });
}

const queue = load();
if (has('--sync')) sync(queue);
else if (!existsSync(queuePath)) sync(queue);

const itemId = flag('--item') ?? flag('--claim') ?? flag('--finish');
if (has('--claim')) {
  const item = queue.items.find((entry) => entry.itemId === itemId);
  if (!item) {
    console.error(`[fail] unknown itemId ${itemId}; run --sync --list first`);
    process.exit(2);
  }
  item.status = 'running';
  item.claims.push({ at: new Date().toISOString(), pid: Number(flag('--pid', '0')) || null, note: flag('--note', null) });
  save(queue);
  console.log(JSON.stringify({ claimed: item.itemId, purpose: item.purpose, priority: item.priority }, null, 2));
} else if (has('--finish')) {
  const item = queue.items.find((entry) => entry.itemId === itemId);
  if (!item) {
    console.error(`[fail] unknown itemId ${itemId}`);
    process.exit(2);
  }
  const status = flag('--status', 'completed');
  if (!['completed', 'failed', 'blocked'].includes(status)) {
    console.error(`[fail] --status must be completed|failed|blocked`);
    process.exit(2);
  }
  item.status = status;
  item.runs.push({
    at: new Date().toISOString(),
    status,
    evidence: flag('--evidence', null),
    note: flag('--note', null),
  });
  save(queue);
  console.log(JSON.stringify({ finished: item.itemId, status, evidence: flag('--evidence', null) }, null, 2));
} else if (has('--next')) {
  const next = ordered(queue)[0] ?? null;
  console.log(JSON.stringify(next ? {
    itemId: next.itemId, lane: next.lane, priority: next.priority, status: next.status,
    purpose: next.purpose, model: next.model, command: next.command, questions: next.questions,
  } : { next: null, note: 'no open requests' }, null, 2));
} else {
  save(queue);
  console.log(JSON.stringify({
    queuePath,
    counts: queue.items.reduce((acc, item) => ({ ...acc, [item.status]: (acc[item.status] ?? 0) + 1 }), {}),
    open: ordered(queue).map((item) => `${item.priority} ${item.itemId} [${item.status}] ${item.purpose}`.slice(0, 160)),
    orphans: queue.orphanRequests.length,
  }, null, 2));
}
