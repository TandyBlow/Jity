import { describe, expect, test } from 'vitest';
import { HeartbeatScheduler, type HeartbeatClock, type HeartbeatIo, type HeartbeatOptions, type HeartbeatLoss, type LeaseHeartbeatState, type ClaimHeartbeatState } from './heartbeat';
import { isAbortError } from './engine';
import { SerialInferenceQueue } from './inference-queue';
import { WorldApiError, WorldTimeoutError } from '../transport';
import type { RequestMap, Scope } from '../types';

/** Deterministic clock: advance() fires due timers in schedule order. */
class ManualClock implements HeartbeatClock {
  private nowMs = 0;
  private seq = 0;
  private readonly timers: { at: number; fn: () => void; cancelled: boolean; seq: number }[] = [];
  now(): number { return this.nowMs; }
  set(delayMs: number, fn: () => void): () => void {
    const entry = { at: this.nowMs + Math.max(0, delayMs), fn, cancelled: false, seq: this.seq++ };
    this.timers.push(entry);
    return () => { entry.cancelled = true; };
  }
  advance(ms: number): void {
    const target = this.nowMs + ms;
    for (;;) {
      const due = this.timers.filter((t) => !t.cancelled && t.at <= target).sort((a, b) => a.at - b.at || a.seq - b.seq)[0];
      if (!due) break;
      this.nowMs = due.at;
      due.cancelled = true;
      due.fn();
    }
    this.nowMs = target;
  }
}

function leaseData(expiresAtEpochMilli: number) {
  return { leaseToken: 'lease_a', fenceEpoch: 7, expiresAtEpochMilli };
}
function claimData(expiresAtEpochMilli: number) {
  return { pointId: 'root_0', mode: 'head', generation: 1, fenceEpoch: 7, issuedAtEpochMilli: 1792617599000, expiresAtEpochMilli };
}

function apiError(code: string): WorldApiError {
  return new WorldApiError({
    protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 1, canonicalVersion: 'world-canonical-v1',
    serverTimeEpochMilli: 1, replayed: false, operation: null, requestId: null, worldId: 'w',
    world: null, control: null, work: null,
    error: { code, httpStatus: 409, retryable: false, clientAction: 'none', details: {} },
  } as never);
}

function harness() {
  const clock = new ManualClock();
  const calls = {
    lease: [] as Array<{ request: RequestMap['lease_renew']; scope: Scope }>,
    claim: [] as Array<{ request: RequestMap['narration_claim_renew']; scope: Scope }>,
  };
  const handlers = {
    lease: (_request: RequestMap['lease_renew']): Promise<unknown> => Promise.resolve({ data: leaseData(0) }),
    claim: (_request: RequestMap['narration_claim_renew']): Promise<unknown> => Promise.resolve({ data: claimData(0) }),
  };
  const losses: HeartbeatLoss[] = [];
  const renewals = { lease: [] as number[], claim: [] as number[] };
  let requestId = 0;
  const options: HeartbeatOptions = { leadMs: 30_000, retryBackoffMs: 5_000, clock, nextRequestId: () => `hb_${++requestId}` };
  const io: HeartbeatIo = {
    renewLease: (request, scope) => {
      calls.lease.push({ request, scope });
      return handlers.lease(request) as never;
    },
    renewClaim: (request, scope) => {
      calls.claim.push({ request, scope });
      return handlers.claim(request) as never;
    },
  };
  const scheduler = new HeartbeatScheduler(io, options, {
    onLeaseRenewed: (expiresAt) => renewals.lease.push(expiresAt),
    onClaimRenewed: (expiresAt) => renewals.claim.push(expiresAt),
    onLost: (loss) => losses.push(loss),
  });
  return { clock, calls, handlers, losses, renewals, scheduler, io };
}

const LEASE: LeaseHeartbeatState = { worldId: 'world_school', leaseToken: 'lease_a', fenceEpoch: 7, expiresAtEpochMilli: 120_000 };
const CLAIM: ClaimHeartbeatState = {
  worldId: 'world_school', pointId: 'root_0', claimToken: 'claim_root', generation: 1,
  issuedAtEpochMilli: 1792617599000, leaseToken: 'lease_a', fenceEpoch: 7, expiresAtEpochMilli: 60_000,
};

/** advance() fires synchronously; renew adoption settles on microtasks. */
async function settle(): Promise<void> {
  for (let i = 0; i < 4; i++) await Promise.resolve();
}

describe('HeartbeatScheduler', () => {
  test('lease renewal fires at expiry minus lead, adopts the new receipt and reschedules', async () => {
    const h = harness();
    h.handlers.lease = () => Promise.resolve({ data: leaseData(240_000) });
    h.scheduler.startLease(LEASE);
    h.clock.advance(90_000 - 1);
    expect(h.calls.lease).toHaveLength(0); // not yet: fires at expiry(120k) − lead(30k)
    h.clock.advance(1);
    await settle(); // adoption runs on microtasks
    expect(h.calls.lease).toHaveLength(1);
    expect(h.calls.lease[0]!.request).toEqual({ protocolVersion: 2, requestId: 'hb_1', worldId: 'world_school', leaseToken: 'lease_a', fenceEpoch: 7 });
    expect(h.calls.lease[0]!.scope).toEqual({ worldId: 'world_school' });
    expect(h.renewals.lease).toEqual([240_000]);
    h.clock.advance(119_999); // next fire at 240k − 30k
    expect(h.calls.lease).toHaveLength(1);
    h.clock.advance(1);
    await settle();
    expect(h.calls.lease).toHaveLength(2);
  });

  test('claim renewal carries the full head-mode binding and point scope', async () => {
    const h = harness();
    h.handlers.claim = () => Promise.resolve({ data: claimData(120_000) });
    h.scheduler.startClaim(CLAIM);
    h.clock.advance(30_000); // expiry(60k) − lead(30k)
    await settle();
    expect(h.calls.claim).toHaveLength(1);
    expect(h.calls.claim[0]!.request).toEqual({
      protocolVersion: 2, requestId: 'hb_1', worldId: 'world_school', pointId: 'root_0', mode: 'head',
      claimToken: 'claim_root', generation: 1, issuedAtEpochMilli: 1792617599000, leaseToken: 'lease_a', fenceEpoch: 7,
    });
    expect(h.calls.claim[0]!.scope).toEqual({ worldId: 'world_school', pointId: 'root_0' });
    expect(h.renewals.claim).toEqual([120_000]);
  });

  test('a timeout retries with the same requestId and then succeeds', async () => {
    const h = harness();
    let attempts = 0;
    h.handlers.lease = () => {
      attempts += 1;
      return attempts === 1 ? Promise.reject(new WorldTimeoutError('lost')) : Promise.resolve({ data: leaseData(240_000) });
    };
    h.scheduler.startLease(LEASE);
    h.clock.advance(90_000); // fire #1: timeout
    await settle(); // rejection schedules the backoff on microtasks
    expect(h.calls.lease).toHaveLength(1);
    h.clock.advance(5_000); // backoff retry
    await settle();
    expect(h.calls.lease).toHaveLength(2);
    expect(h.calls.lease[1]!.request.requestId).toBe(h.calls.lease[0]!.request.requestId); // same id — idempotent replay
    expect(h.renewals.lease).toEqual([240_000]);
    expect(h.losses).toHaveLength(0);
  });

  test('a definitive lease rejection is a loss: reported once, heartbeat stops', async () => {
    const h = harness();
    h.handlers.lease = () => Promise.reject(apiError('stale_epoch'));
    h.scheduler.startLease(LEASE);
    h.clock.advance(90_000);
    await settle();
    expect(h.losses.map((loss) => loss.kind)).toEqual(['lease']);
    expect(h.losses[0]!.code).toBe('stale_epoch');
    h.clock.advance(600_000); // nothing left to fire
    expect(h.calls.lease).toHaveLength(1);
  });

  test('a claim loss stops only the claim heartbeat; the lease keeps beating', async () => {
    const h = harness();
    h.handlers.claim = () => Promise.reject(apiError('claim_fenced'));
    h.handlers.lease = () => Promise.resolve({ data: leaseData(240_000) });
    h.scheduler.startLease(LEASE);
    h.scheduler.startClaim(CLAIM);
    h.clock.advance(30_000); // claim fires first (60k−30k) and is lost
    await settle();
    expect(h.losses.map((loss) => loss.kind)).toEqual(['claim']);
    expect(h.losses[0]!.code).toBe('claim_fenced');
    h.clock.advance(60_000); // lease fires at 90k
    await settle();
    expect(h.calls.lease).toHaveLength(1);
    expect(h.renewals.lease).toEqual([240_000]);
  });

  test('a state update reschedules and voids the superseded in-flight renewal', async () => {
    const h = harness();
    let releaseHeld: ((value: unknown) => void) | null = null;
    h.handlers.lease = () => new Promise((resolve) => { releaseHeld = resolve; });
    h.scheduler.startLease(LEASE);
    h.clock.advance(90_000); // fire #1 with the OLD token; response held
    expect(h.calls.lease).toHaveLength(1);
    h.scheduler.updateLease({ ...LEASE, leaseToken: 'lease_b', expiresAtEpochMilli: 300_000 });
    releaseHeld!({ data: leaseData(400_000) }); // the OLD renewal settles late (guard above: the call fired)
    await settle();
    expect(h.renewals.lease).toEqual([]); // superseded adoption discarded
    h.handlers.lease = () => Promise.resolve({ data: leaseData(600_000) });
    h.clock.advance(180_000); // new fire at 300k − 30k = 270k (we are at 90k)
    expect(h.calls.lease).toHaveLength(2);
    expect(h.calls.lease[1]!.request.leaseToken).toBe('lease_b'); // the CURRENT token, not the superseded one
  });

  test('a regressed lease observation is dropped; only strictly newer state replaces', () => {
    const h = harness();
    h.handlers.lease = () => Promise.resolve({ data: leaseData(600_000) });
    h.scheduler.startLease(LEASE); // epoch 7, exp 120k
    h.scheduler.updateLease({ worldId: 'world_school', leaseToken: 'lease_b', fenceEpoch: 8, expiresAtEpochMilli: 300_000 }); // fresher
    // A late envelope with the OLD credentials arrives afterwards:
    h.scheduler.updateLease({ ...LEASE }); // epoch 7 < 8 — must be dropped
    h.clock.advance(90_000); // the original schedule (120k − 30k) is gone
    expect(h.calls.lease).toHaveLength(0);
    h.clock.advance(180_000); // fire at 300k − 30k
    expect(h.calls.lease).toHaveLength(1);
    expect(h.calls.lease[0]!.request.leaseToken).toBe('lease_b'); // the CURRENT token
    expect(h.calls.lease[0]!.request.fenceEpoch).toBe(8);
  });

  test('a same-epoch lease receipt with a newer expiry replaces the schedule', () => {
    const h = harness();
    h.handlers.lease = () => Promise.resolve({ data: leaseData(600_000) });
    h.scheduler.startLease(LEASE); // epoch 7, exp 120k → fire at 90k
    h.scheduler.updateLease({ ...LEASE, expiresAtEpochMilli: 240_000 }); // renew receipt, same epoch
    h.clock.advance(90_000);
    expect(h.calls.lease).toHaveLength(0); // rescheduled to 210k
    h.clock.advance(120_000);
    expect(h.calls.lease).toHaveLength(1);
  });

  test('updateClaim is symmetric and guarded by claim freshness', () => {
    const h = harness();
    h.handlers.claim = () => Promise.resolve({ data: claimData(900_000) });
    h.scheduler.startClaim(CLAIM); // gen 1, exp 60k → fire at 30k
    h.scheduler.updateClaim({ ...CLAIM, expiresAtEpochMilli: 120_000 }); // renew receipt: same gen, newer expiry → accepted
    h.clock.advance(30_000);
    expect(h.calls.claim).toHaveLength(0); // rescheduled to 90k
    // A regressed observation is dropped — even one carrying a stale token,
    // which under an unconditional replace would renew with dead credentials:
    h.scheduler.updateClaim({ ...CLAIM, claimToken: 'claim_stale', expiresAtEpochMilli: 60_000 });
    h.clock.advance(60_000); // fire at 90k with the CURRENT claim
    expect(h.calls.claim).toHaveLength(1);
    expect(h.calls.claim[0]!.request.claimToken).toBe('claim_root'); // never claim_stale
    expect(h.calls.claim[0]!.request.generation).toBe(1);
    // A fresh claim (generation bump) replaces the state:
    h.scheduler.updateClaim({ ...CLAIM, claimToken: 'claim_new', generation: 2, issuedAtEpochMilli: CLAIM.issuedAtEpochMilli + 1, expiresAtEpochMilli: 300_000 });
    h.clock.advance(180_000); // fire at 300k − 30k = 270k (we are at 90k)
    expect(h.calls.claim).toHaveLength(2);
    expect(h.calls.claim[1]!.request.claimToken).toBe('claim_new');
    expect(h.calls.claim[1]!.request.generation).toBe(2);
  });

  test('stop cancels both timers permanently', () => {
    const h = harness();
    h.scheduler.startLease(LEASE);
    h.scheduler.startClaim(CLAIM);
    h.scheduler.stop();
    h.clock.advance(10_000_000);
    expect(h.calls.lease).toHaveLength(0);
    expect(h.calls.claim).toHaveLength(0);
  });

  test('a renewal runs and completes while a generation holds the inference queue', async () => {
    const h = harness();
    h.handlers.lease = () => Promise.resolve({ data: leaseData(240_000) });
    const queue = new SerialInferenceQueue();
    let releaseGeneration: (() => void) | null = null;
    const generation = queue.run({ label: 'narration', start: () => new Promise<string>((resolve) => { releaseGeneration = () => resolve('late text'); }) });
    h.scheduler.startLease(LEASE);
    h.clock.advance(90_000); // renewal fires while the engine call is held
    await settle();
    expect(h.renewals.lease).toEqual([240_000]); // transport path, not queued behind inference
    releaseGeneration!(); // the queue entry started (no assertion fired before)
    expect((await generation).value).toBe('late text');
  });

  test('a definitive loss aborts the in-flight generation through causal onLost wiring', async () => {
    // The session pattern under test: onLost itself cancels work — the
    // heartbeat's loss report IS the abort cause, not a follow-up call.
    const h = harness();
    h.handlers.lease = () => Promise.reject(apiError('stale_epoch'));
    const queue = new SerialInferenceQueue();
    let releaseGeneration: (() => void) | null = null;
    const session = new AbortController();
    const generation = queue.run({ label: 'action', signal: session.signal, start: () => new Promise<string>((resolve) => { releaseGeneration = () => resolve('late work for a dead lease'); }) });
    const wired = new HeartbeatScheduler(h.io, {
      leadMs: 30_000, retryBackoffMs: 5_000, clock: h.clock, nextRequestId: () => 'hb_wired',
    }, {
      onLeaseRenewed: () => {},
      onClaimRenewed: () => {},
      onLost: () => session.abort(), // causal wiring: the loss report IS the abort cause
    });
    wired.startLease(LEASE);
    h.clock.advance(90_000);
    await settle();
    await expect(generation).rejects.toSatisfy(isAbortError);
    releaseGeneration!(); // late settle must stay discarded
    await expect(generation).rejects.toSatisfy(isAbortError);
    expect(queue.depth).toBe(0); // slot freed once the engine settles
  });
});
