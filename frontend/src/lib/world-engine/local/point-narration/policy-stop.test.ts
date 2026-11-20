import { describe, expect, it } from 'vitest';
import { ControllerDriver, initialMemory, type WorldModelPort } from '../../controller';
import type { ModelTask } from '../../schedule';
import type { InitialTemplate, Json } from '../../types';
import { SHORT_STATE } from '../../runtime/b3-short-samples';
import { LocalWorldTransport } from '../transport';

function template(): InitialTemplate {
  const initial = structuredClone(SHORT_STATE.initial) as InitialTemplate & { worldId?: string };
  delete initial.worldId;
  return initial;
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

/** A continuation policy stop is an automatic round ending, not a player
 * cancel. Its cancel operation must wait for the committed head prose, then
 * succeed on the same point; it must not resend the refused cancel forever. */
describe('policy stop waits for the committed point prose', () => {
  it('cancels after the held head narration is ready, without re-settling', async () => {
    const initial = template();
    const order = Object.keys(initial.characters).sort();
    const actor = order[0]!;
    const p1NarrationStarted = deferred<void>();
    const p1Committed = deferred<void>();
    const allCommitted = deferred<void>();
    const committed: string[] = [];
    const cancelSeen = deferred<void>();
    const releaseP1 = deferred<string>();
    let cancelSignalled = false;
    let commits = 0;
    let p1Finished = false;

    const model: WorldModelPort = {
      async generate(task: ModelTask, key: string, input: Json): Promise<Json> {
        if (task === 'pointPlan') {
          return [
            { pointId: 'p1', kind: 'normal', timeAdvance: { boundary: 'elapsed', duration: { amount: 1, unit: 'minute' } }, actorIds: [actor] },
            { pointId: 'p2', kind: 'normal', timeAdvance: { boundary: 'elapsed', duration: { amount: 1, unit: 'minute' } }, actorIds: [order[1]!] },
          ];
        }
        if (task === 'action') return { kind: 'act', text: '我继续走向门厅。' };
        if (task === 'targets') return { targets: [] };
        if (task === 'results') return { [key]: '门厅里没有人回应。' };
        if (task === 'updates') return [];
        if (task === 'continuation') return { kind: 'policy_stop', reason: 'test_policy_stop' };
        if (task === 'narration') {
          if (key === 'root' || key.startsWith('point_root_')) return '根点叙事。';
          if (key === 'p1') {
            p1NarrationStarted.resolve();
            const text = await releaseP1.promise;
            p1Finished = true;
            return text;
          }
          if (key === 'p2') return '第二点的正文。';
          throw new Error(`unexpected narration ${key}`);
        }
        throw new Error(`unexpected task ${task}`);
      },
    };

    const transport = await LocalWorldTransport.create(initial, { roll: () => 13 });
    const execute = transport.execute.bind(transport);
    transport.execute = (async (operation, request, scope) => {
      if (operation === 'round_conclusion_cancel' && !cancelSignalled) {
        cancelSignalled = true;
        cancelSeen.resolve();
      }
      return execute(operation, request, scope);
    }) as typeof transport.execute;

    const memory = initialMemory('policy_stop', 'holder_policy_stop');
    memory.initialTemplate = initial;
    memory.playerInput = { text: '我走进门厅。', order };
    memory.allocPlan = {
      allocationKey: 'policy_stop_command',
      slots: [
        { slotKey: 'advance', kind: 'advance' }, { slotKey: 'input', kind: 'input' },
        { slotKey: 'round', kind: 'round' }, { slotKey: 'point', kind: 'point' },
        ...order.map((actorId) => ({ slotKey: `group:${actorId}`, kind: 'group' as const })),
      ],
    };
    const driver = new ControllerDriver({
      transport, model,
      onCommit: (event) => {
        if (event.phase !== 'committed') return;
        const request = event.request as { pointId?: string };
        if (request.pointId) {
          commits += 1;
          committed.push(request.pointId);
          if (request.pointId === 'p1') p1Committed.resolve();
          if (committed.length === 2) allCommitted.resolve();
        }
      },
    }, memory, undefined, { narrationOverlap: true });

    const run = driver.run();
    await p1Committed.promise;
    await p1NarrationStarted.promise;
    await allCommitted.promise;
    expect(p1Finished).toBe(false);
    await cancelSeen.promise;
    // The cancel reached the server while p1 prose was still pending. Old
    // inline narration retried this refusal without waiting and stalled.
    await new Promise((resolve) => setTimeout(resolve, 1500));
    releaseP1.resolve('门厅里只剩下一盏灯。');
    const status = await run;

    expect(status.kind).not.toBe('error');
    if (status.kind === 'stop') expect(status.reason).not.toContain('stalled');
    expect(commits).toBe(2);
    expect(committed).toEqual(['p1', 'p2']);
    const record = transport.snapshot();
    expect(record.narrations.p1).toMatchObject({ status: 'ready', text: '门厅里只剩下一盏灯。' });
    expect(record.narrations.p2).toMatchObject({ status: 'ready', text: '第二点的正文。' });
    expect(record.advance).toBeNull();
    expect(record.round?.conclusion).toMatchObject({ kind: 'handback', closedBy: 'cancel', cancelReason: 'test_policy_stop' });
  }, 30000);
});
