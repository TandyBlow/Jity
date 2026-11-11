import { describe, expect, it } from 'vitest';
import type { WorldModelPort } from '../../controller';
import type { RequestMap, Success, WorldContext, WorldOperation, Scope } from '../../types';
import { SHORT_STATE } from '../../runtime/b3-short-samples';
import { WorldApiError } from '../../transport';
import { PointNarrationQueue } from './queue';

/** A controlled point queue: p1 answers empty, p2 answers prose. The queue must
 * keep the empty status on p1 and still finish p2; neither gets program text. */
function fakeTransport() {
  const entries: Record<string, { status: 'pending' | 'ready' | 'failed'; text: string | null; claim: string }> = {
    p1: { status: 'pending', text: null, claim: 'claim_p1' },
    p2: { status: 'pending', text: null, claim: 'claim_p2' },
  };
  const submits: Array<{ pointId: string; outcome: string; text: string | null; reason: string | null }> = [];
  const submitModes: Array<'head' | 'history'> = [];
  let p1SubmitAttempts = 0;
  let head = 'p1';
  const context = (): WorldContext => ({
    worldId: 'w', head: { pointId: head, version: head === 'p1' ? 1 : 2, stateDigest: 'd', narrationStatus: entries[head].status },
    advance: { advanceId: 'a', inputId: 'i', intentStatus: 'consumed', inputAvailable: false },
    round: { roundId: 'r', trigger: 'player', order: ['person_a', 'person_c'], cursor: 2, actedIds: ['person_a', 'person_c'], visitedIds: ['person_a', 'person_c'], conclusion: null },
    time: SHORT_STATE.time as WorldContext['time'], lease: { fenceEpoch: 1, expiresAtEpochMilli: 999999 },
    successor: null, activePointId: null, activeRoundId: 'r',
  });
  const transport = {
    async execute<K extends WorldOperation>(operation: K, request: RequestMap[K], scope: Scope): Promise<Success<K>> {
      if (operation === 'get_context') {
        return { protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 2, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1, world: context(), control: { phase: 'select_actor', paused: false, revision: 1, gate: { status: 'pending', generation: 1, issuedAtEpochMilli: 1, expiresAtEpochMilli: 2 }, blockedReasons: ['narration_pending'], canCompute: false }, work: null, activeInput: null, recovery: null } as unknown as Success<K>;
      }
      if (operation === 'narration_get') {
        const pointId = scope.pointId!;
        return { protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 2, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1, world: context(), data: { pointId, narrationStatus: entries[pointId].status, generation: 1, text: entries[pointId].text } } as unknown as Success<K>;
      }
      if (operation === 'narration_claim') {
        const pointId = (scope.pointId ?? 'p1')!;
        return { protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 2, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1, replayed: false, operation, requestId: 'r', requestHash: 'h', world: context(), control: { phase: 'select_actor', paused: false, revision: 1, gate: { status: 'none' }, blockedReasons: [], canCompute: true }, work: null, data: { pointId, mode: 'head', generation: 1, fenceEpoch: 1, issuedAtEpochMilli: 1, expiresAtEpochMilli: 999999, claimToken: entries[pointId].claim } } as unknown as Success<K>;
      }
      if (operation === 'get_state') {
        return { protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 2, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1, world: context(), data: { pointId: (request as RequestMap['get_state']).point ?? 'p1', version: 1, state: SHORT_STATE, stateDigest: 'd', previousPointId: null, timeAdvance: null, entityDeltas: {} } } as unknown as Success<K>;
      }
      if (operation === 'narration_submit') {
        const submit = request as RequestMap['narration_submit'];
        submitModes.push(submit.mode);
        if (submit.pointId === 'p1' && ++p1SubmitAttempts === 1) {
          // p2 took the head after p1 claimed it; the first p1 submit is fenced.
          head = 'p2';
          throw new WorldApiError({ protocolVersion: 2, error: { code: 'claim_expired', message: 'p1 claim expired' } } as never);
        }
        submits.push({ pointId: submit.pointId, outcome: submit.outcome, text: submit.text, reason: submit.failureReason });
        entries[submit.pointId].status = submit.outcome;
        entries[submit.pointId].text = submit.text;
        if (submit.pointId === 'p1') head = 'p2';
        return { protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 2, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1, replayed: false, operation, requestId: 'r', requestHash: 'h', world: context(), control: { phase: 'select_actor', paused: false, revision: 1, gate: { status: 'none' }, blockedReasons: [], canCompute: true }, work: null, data: { pointId: submit.pointId, narrationStatus: submit.outcome, generation: 1 } } as unknown as Success<K>;
      }
      if (operation === 'list_points') return { protocolVersion: 2, engineVersion: 'world-engine-v1', schemaVersion: 2, canonicalVersion: 'world-canonical-v1', serverTimeEpochMilli: 1, world: context(), data: { points: [{ pointId: 'p1', sequence: 1, kind: 'normal', roundId: 'r', advanceId: 'a', stateDigest: 'd' }, { pointId: 'p2', sequence: 2, kind: 'normal', roundId: 'r', advanceId: 'a', stateDigest: 'd' }] } } as unknown as Success<K>;
      throw new Error(`unexpected ${operation}`);
    },
  };
  return { transport, entries, submits, submitModes };
}

describe('point narration queue empty/error outcomes', () => {
  it('keeps an empty point empty and still finishes the next point', async () => {
    const fake = fakeTransport();
    const model: WorldModelPort = {
      async generate(task, key) {
        if (task !== 'narration') throw new Error(`unexpected ${task}`);
        return key === 'p1' ? '   ' : '第二点的正文。';
      },
    };
    let seq = 0;
    const queue = new PointNarrationQueue({
      transport: fake.transport, model, worldId: 'w', requestId: () => `q_${++seq}`,
      lease: () => ({ leaseToken: 'lease', fenceEpoch: 1 }),
    });
    queue.enqueue('p1');
    queue.enqueue('p2');
    await queue.settled();
    expect(fake.entries.p1).toMatchObject({ status: 'failed', text: null });
    expect(fake.entries.p2).toMatchObject({ status: 'ready', text: '第二点的正文。' });
    expect(fake.submits).toEqual([
      { pointId: 'p1', outcome: 'failed', text: null, reason: 'empty_model_output' },
      { pointId: 'p2', outcome: 'ready', text: '第二点的正文。', reason: null },
    ]);
  });

  it('leaves the same point pending when the model is cancelled', async () => {
    const fake = fakeTransport();
    const model: WorldModelPort = {
      async generate() {
        const error = new Error('model_output_discarded_by_cancel');
        error.name = 'AbortError';
        throw error;
      },
    };
    let seq = 0;
    const outcomes: string[] = [];
    const queue = new PointNarrationQueue({
      transport: fake.transport, model, worldId: 'w', requestId: () => `q_${++seq}`,
      lease: () => ({ leaseToken: 'lease', fenceEpoch: 1 }),
      onOutcome: (outcome) => outcomes.push(`${outcome.status}:${outcome.pointId}`),
    });
    queue.enqueue('p1');
    await queue.settled();
    expect(fake.entries.p1).toMatchObject({ status: 'pending', text: null });
    expect(fake.submits).toEqual([]);
    expect(outcomes).toEqual(['skipped:p1']);
  });

  it('reclaims the same point when a late p1 submit is fenced by p2', async () => {
    const fake = fakeTransport();
    let calls = 0;
    const model: WorldModelPort = {
      async generate() { calls += 1; return 'p1 的正文。'; },
    };
    let seq = 0;
    const queue = new PointNarrationQueue({
      transport: fake.transport, model, worldId: 'w', requestId: () => `q_${++seq}`,
      lease: () => ({ leaseToken: 'lease', fenceEpoch: 1 }),
    });
    queue.enqueue('p1');
    await queue.settled();
    expect(calls).toBe(1);
    expect(fake.entries.p1).toMatchObject({ status: 'ready', text: 'p1 的正文。' });
    expect(fake.submits).toEqual([{ pointId: 'p1', outcome: 'ready', text: 'p1 的正文。', reason: null }]);
    expect(fake.submitModes).toEqual(['head', 'history']);
  });
});
